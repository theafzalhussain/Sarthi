"""
OpenAI-compatible provider.

GROQ, OPENROUTER aur NVIDIA — teeno OpenAI ka API format use karte hain.
Isliye ek hi class teeno ke liye kaafi hai — sirf base URL alag.

Fayda: kal koi naya provider aaya jo OpenAI-compatible hai, to sirf
BASE_URLS mein ek line daalni hai. Bas. Baaki kuch nahi badalta.

(NVIDIA add karne mein exactly yahi hua — ek line.)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import LLMProvider
from .types import BrainError, LLMResponse, Message, Role, ToolCall, ToolSchema

# Provider ka naam -> API base URL
#
# Naya OpenAI-compatible provider add karna hai? Bas yahan ek line.
# Koi naya class likhne ki zarurat nahi.
BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    # NVIDIA NIM — free tier, key build.nvidia.com se (nvapi- se shuru hoti hai)
    "nvidia": "https://integrate.api.nvidia.com/v1",
    # Bluesminds — multi-model gateway, 200+ models, OpenAI-compatible
    "bluesminds": "https://api.bluesminds.com/v1",
}


class OpenAICompatProvider(LLMProvider):
    """Groq / OpenRouter / koi bhi OpenAI-compatible API."""

    def __init__(self, config: ProviderConfig, base_url: str | None = None):
        super().__init__(config)
        self.base_url = base_url or BASE_URLS.get(config.name)
        if not self.base_url:
            raise BrainError(
                f"'{config.name}' ke liye base URL nahi mila. "
                f"BASE_URLS mein add kar."
            )

    # ------------------------------------------------------------------
    #  Message conversion
    # ------------------------------------------------------------------

    def _convert_message(self, msg: Message) -> dict[str, Any]:
        """Hamara Message -> OpenAI format."""

        # Tool ka result
        if msg.role == Role.TOOL:
            return {
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id or "",
            }

        # Assistant ne tool call kiya
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }

        # Image wala message (vision models ke liye)
        if msg.has_image:
            return {
                "role": msg.role.value,
                "content": [
                    {"type": "text", "text": msg.content},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{msg.image_mime};base64,{msg.image_b64}"
                        },
                    },
                ],
            }

        # Normal message
        return {"role": msg.role.value, "content": msg.content}

    def _parse_tool_calls(self, raw_calls: list[dict]) -> list[ToolCall]:
        """OpenAI ke tool_calls -> hamare ToolCall objects."""
        calls: list[ToolCall] = []

        for raw in raw_calls or []:
            fn = raw.get("function", {})
            name = fn.get("name", "")
            if not name:
                continue

            # Arguments JSON string hota hai — parse karo
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                # LLM ne kharab JSON diya — khali args ke saath aage badho
                args = {}

            calls.append(
                ToolCall(
                    id=raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                )
            )

        return calls

    # ------------------------------------------------------------------
    #  Model discovery
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """
        `/models` endpoint se available models nikaalo.

        Groq aur OpenRouter dono ye endpoint dete hain.
        """
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise BrainError(f"{self.name}: models list nahi mili — {exc}") from exc

        if resp.status_code >= 400:
            raise BrainError(
                f"{self.name}: HTTP {resp.status_code} — {resp.text[:200]}"
            )

        data = resp.json()
        items = data.get("data") or data.get("models") or []

        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("name")
                if model_id:
                    names.append(str(model_id))
            elif isinstance(item, str):
                names.append(item)

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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._convert_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        # OpenRouter ye headers maangta hai (optional but polite)
        if self.name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/saarthi-agent"
            headers["X-Title"] = "SAARTHI"

        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise BrainError(f"{self.name}: network problem — {exc}") from exc

        # Rate limit — free tier mein ye aayega, isliye clear message
        if resp.status_code == 429:
            raise BrainError(
                f"{self.name}: free tier limit khatam ho gayi. "
                f"Thodi der baad try kar, ya doosra provider use hoga."
            )

        if resp.status_code == 401:
            raise BrainError(
                f"{self.name}: API key galat hai. .env file check kar."
            )

        # Model deprecate ho gaya — ye BAHUT common hai, isliye
        # clear + actionable message dete hain
        if resp.status_code == 404:
            raise BrainError(
                f"{self.name}: model '{self.model}' nahi mila — shayad "
                f"deprecate ho gaya.\n"
                f"  Fix: CLI mein '/models' chala, available models dikhenge.\n"
                f"  Phir .env mein {self.name.upper()}_MODEL update kar de.\n"
                f"  (server ne kaha: {resp.text[:200]})"
            )

        if resp.status_code >= 400:
            raise BrainError(
                f"{self.name}: HTTP {resp.status_code} — {resp.text[:300]}"
            )

        data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise BrainError(f"{self.name}: khali jawab aaya")

        message = choices[0].get("message", {})
        usage = data.get("usage", {})

        return LLMResponse(
            text=(message.get("content") or "").strip(),
            tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
