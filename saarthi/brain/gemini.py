"""
Google Gemini provider.

Ye SAARTHI ka "aankh" hai — screenshot dekh ke samajh sakta hai
ki screen pe kya hai. Phone control ke liye ye ZARURI hai.

Gemini ka API format OpenAI se alag hai, isliye alag class.
Free tier: https://aistudio.google.com/apikey
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import LLMProvider
from .types import BrainError, LLMResponse, Message, Role, ToolCall, ToolSchema

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    """Google Gemini — vision support ke saath."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

    # ------------------------------------------------------------------
    #  Message conversion (Gemini ka apna format hai)
    # ------------------------------------------------------------------

    def _build_contents(
        self, messages: list[Message]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Hamare messages -> Gemini ke 'contents'.

        Returns:
            (contents, system_instruction)
        """
        contents: list[dict[str, Any]] = []
        system_text: list[str] = []

        for msg in messages:
            # Gemini system message ko alag field mein leta hai
            if msg.role == Role.SYSTEM:
                if msg.content:
                    system_text.append(msg.content)
                continue

            # Tool ka result
            if msg.role == Role.TOOL:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    # tool_call_id mein humne naam store kiya hai
                                    "name": msg.tool_call_id or "tool",
                                    "response": {"result": msg.content},
                                }
                            }
                        ],
                    }
                )
                continue

            # Gemini "assistant" ko "model" bolta hai
            role = "model" if msg.role == Role.ASSISTANT else "user"
            parts: list[dict[str, Any]] = []

            # Assistant ne tool call kiya tha
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append(
                        {"functionCall": {"name": tc.name, "args": tc.arguments}}
                    )

            if msg.content:
                parts.append({"text": msg.content})

            # Screenshot / image
            if msg.has_image:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": msg.image_mime,
                            "data": msg.image_b64,
                        }
                    }
                )

            if not parts:
                continue

            contents.append({"role": role, "parts": parts})

        system_instruction = "\n\n".join(system_text) if system_text else None
        return contents, system_instruction

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Gemini ka jawab -> hamara LLMResponse."""
        candidates = data.get("candidates") or []
        if not candidates:
            # Safety filter ne block kiya ho sakta hai
            feedback = data.get("promptFeedback", {})
            reason = feedback.get("blockReason")
            if reason:
                raise BrainError(f"gemini: request block hua — {reason}")
            raise BrainError("gemini: khali jawab aaya")

        parts = candidates[0].get("content", {}).get("parts") or []

        text_chunks: list[str] = []
        tool_calls: list[ToolCall] = []

        for part in parts:
            if "text" in part:
                text_chunks.append(part["text"])

            if "functionCall" in part:
                fc = part["functionCall"]
                name = fc.get("name", "")
                if not name:
                    continue
                args = fc.get("args") or {}
                tool_calls.append(
                    ToolCall(
                        # Gemini id nahi deta — hum khud banate hain.
                        # Naam bhi rakhte hain kyunki functionResponse mein
                        # naam se match karna padta hai.
                        id=name,
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )

        usage = data.get("usageMetadata", {})

        return LLMResponse(
            text="".join(text_chunks).strip(),
            tool_calls=tool_calls,
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
        )

    # ------------------------------------------------------------------
    #  Model discovery
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """Gemini pe available models nikaalo."""
        url = f"{API_BASE}/models"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params={"key": self.config.api_key})
        except httpx.RequestError as exc:
            raise BrainError(f"gemini: models list nahi mili — {exc}") from exc

        if resp.status_code >= 400:
            raise BrainError(f"gemini: HTTP {resp.status_code} — {resp.text[:200]}")

        names: list[str] = []
        for item in resp.json().get("models", []):
            name = item.get("name", "")
            # "models/gemini-3.6-flash" -> "gemini-3.6-flash"
            if name.startswith("models/"):
                name = name[len("models/") :]

            # Sirf wahi models jo generateContent support karte hain
            methods = item.get("supportedGenerationMethods", [])
            if name and (not methods or "generateContent" in methods):
                names.append(name)

        return sorted(names)

    # ------------------------------------------------------------------
    #  Main call
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        contents, system_instruction = self._build_contents(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = [
                {"functionDeclarations": [t.to_gemini_format() for t in tools]}
            ]

        url = f"{API_BASE}/models/{self.model}:generateContent"

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    params={"key": self.config.api_key},
                )
        except httpx.RequestError as exc:
            raise BrainError(f"gemini: network problem — {exc}") from exc

        if resp.status_code == 429:
            raise BrainError(
                "gemini: free tier limit khatam. Thodi der baad try kar."
            )

        if resp.status_code in (401, 403):
            raise BrainError("gemini: API key galat hai. .env check kar.")

        # Model deprecate ho gaya — actionable message do
        if resp.status_code == 404:
            raise BrainError(
                f"gemini: model '{self.model}' nahi mila — shayad deprecate "
                f"ho gaya.\n"
                f"  Fix: CLI mein '/models' chala, available models dikhenge.\n"
                f"  Phir .env mein GEMINI_MODEL update kar de.\n"
                f"  (server ne kaha: {resp.text[:200]})"
            )

        if resp.status_code >= 400:
            raise BrainError(
                f"gemini: HTTP {resp.status_code} — {resp.text[:300]}"
            )

        return self._parse_response(resp.json())
