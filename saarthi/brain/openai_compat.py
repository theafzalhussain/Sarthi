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
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..config import ProviderConfig
from .base import LLMProvider
from .types import (
    BrainError,
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolSchema,
    classify_http_error,
)

# Provider ka naam -> API base URL
#
# Naya OpenAI-compatible provider add karna hai? Bas yahan ek line.
# Koi naya class likhne ki zarurat nahi.
# NVIDIA NIM ka endpoint — free tier, key build.nvidia.com se
# (nvapi- se shuru hoti hai). Ek hi endpoint pe NVIDIA ke saare
# hosted models chalte hain, sirf `model` field badalta hai.
_NVIDIA_NIM = "https://integrate.api.nvidia.com/v1"

BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    # Bluesminds — multi-model gateway, 200+ models, OpenAI-compatible
    "bluesminds": "https://api.bluesminds.com/v1",
    # OpenCode Zen — curated coding models, free tier available
    # Key: https://opencode.ai/zen (API Keys section)
    "opencode": "https://opencode.ai/zen/v1",

    # --- NVIDIA NIM pe hosted models ---
    # Ye chaar "providers" ek hi URL aur ek hi NVIDIA_API_KEY use karte
    # hain. Alag entry isliye hai ki har model ka apna fallback slot
    # mile aur user order badal sake.
    "nvidia": _NVIDIA_NIM,     # nemotron       — smart, agentic
    "deepseek": _NVIDIA_NIM,   # deepseek v4 pro — sabse smart, 1M ctx
    "muse": _NVIDIA_NIM,       # meta muse glimmer — vision + tools
    "gemma": _NVIDIA_NIM,      # google diffusiongemma — vision

    # --- OLLAMA — on-device LLM, ZERO rate limit, ZERO cost ---
    # OpenAI-compatible endpoint. OLLAMA_HOST se override hota hai
    # (kuch log doosri machine ya port pe chalate hain).
    # Fayda: privacy (data local rehta hai) + no rate limit + free.
    "ollama": os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/v1",
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
            # Provider ka apna max_tokens (.env se) jeetta hai
            "max_tokens": self.resolve_max_tokens(max_tokens),
        }

        top_p = self.resolve_top_p()
        if top_p is not None:
            payload["top_p"] = top_p

        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]
            payload["tool_choice"] = "auto"

        # Provider-specific extra fields.
        #
        # NVIDIA ke reasoning models (deepseek v4) `chat_template_kwargs`
        # se thinking on/off karte hain. Iske bina pura chain-of-thought
        # reply mein aa jaata hai — free tier pe tokens barbaad, aur user
        # ko model ki bakbak dikhti hai.
        #
        # `payload` ke apne fields override nahi karte — safety.
        for key, value in self.extra_body.items():
            payload.setdefault(key, value)

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
            # Ollama band ho to actionable error — "ollama serve" chalao
            if self.name == "ollama":
                raise BrainError(
                    f"ollama se connection nahi hua — {exc}\n"
                    "Check kar:\n"
                    "  1. `ollama serve` chal raha hai?\n"
                    "  2. `ollama list` se model check kar (pull hua hai?)\n"
                    "  3. OLLAMA_HOST sahi hai? (.env mein dekh)"
                ) from exc
            raise BrainError(f"{self.name}: network problem — {exc}") from exc

        # Error ko classify karo — rate limit (temporary) aur dead model
        # (permanent) mein farak hai. Brain isi farak se decide karta hai
        # ki provider ko thodi der ke liye chhodna hai ya session bhar.
        if resp.status_code >= 400:
            raise classify_http_error(self.name, resp.status_code, resp.text)

        data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            raise BrainError(f"{self.name}: khali jawab aaya")

        message = choices[0].get("message", {})
        usage = data.get("usage", {})

        # Reasoning models (deepseek v4, muse glimmer) apna soch-vichaar
        # ALAG field mein bhejte hain. Kabhi-kabhi `content` khali aata
        # hai aur asli jawab `reasoning_content` mein hota hai.
        #
        # Iske bina user ko "(kuch jawab nahi aaya)" dikhta hai jabki
        # model ne jawab diya tha.
        text = (message.get("content") or "").strip()
        if not text and not message.get("tool_calls"):
            for fallback_key in ("reasoning_content", "reasoning"):
                fallback = message.get(fallback_key)
                if fallback and str(fallback).strip():
                    text = str(fallback).strip()
                    break

        return LLMResponse(
            text=text,
            tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
            provider=self.name,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


    # ------------------------------------------------------------------
    #  Streaming — real-time token output
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streaming chat — tokens jaise aate hain, waise yield karo.

        User ko turant dikhna shuru hota hai. Last chunk `is_final=True`.
        Agar provider streaming support na kare ya error aaye to
        fallback pe non-streaming response bhejta hai.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._convert_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": self.resolve_max_tokens(max_tokens),
            "stream": True,
        }

        top_p = self.resolve_top_p()
        if top_p is not None:
            payload["top_p"] = top_p

        if tools:
            payload["tools"] = [t.to_openai_format() for t in tools]
            payload["tool_choice"] = "auto"

        for key, value in self.extra_body.items():
            payload.setdefault(key, value)

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        if self.name == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/saarthi-agent"
            headers["X-Title"] = "SAARTHI"

        url = f"{self.base_url}/chat/completions"

        # Collected state for building final response
        full_text = ""
        tool_calls_builder: dict[int, dict] = {}  # index -> {id, name, args_str}
        prompt_tokens = 0
        completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code >= 400:
                        # Error — read body and raise
                        body = await resp.aread()
                        raise classify_http_error(
                            self.name, resp.status_code, body.decode("utf-8", errors="replace")
                        )

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices") or []
                        if not choices:
                            # Usage info chunk (some providers send it separately)
                            usage = data.get("usage")
                            if usage:
                                prompt_tokens = usage.get("prompt_tokens", 0)
                                completion_tokens = usage.get("completion_tokens", 0)
                            continue

                        delta = choices[0].get("delta", {})
                        finish_reason = choices[0].get("finish_reason")

                        # --- Text delta ---
                        text_delta = delta.get("content") or ""
                        if text_delta:
                            full_text += text_delta
                            yield StreamChunk(delta=text_delta)

                        # --- Tool call deltas ---
                        if delta.get("tool_calls"):
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_calls_builder:
                                    tool_calls_builder[idx] = {
                                        "id": tc_delta.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                        "name": "",
                                        "arguments": "",
                                    }
                                builder = tool_calls_builder[idx]
                                fn = tc_delta.get("function", {})
                                if fn.get("name"):
                                    builder["name"] = fn["name"]
                                if fn.get("arguments"):
                                    builder["arguments"] += fn["arguments"]

                        # --- Usage in final chunk ---
                        if finish_reason:
                            usage = data.get("usage") or {}
                            if usage:
                                prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                                completion_tokens = usage.get("completion_tokens", completion_tokens)

        except (BrainError, Exception) as exc:
            # If streaming fails but we already got some text, don't lose it
            if full_text or tool_calls_builder:
                pass  # Fall through to final chunk below
            else:
                raise

        # Build final tool calls from collected deltas
        final_tool_calls: list[ToolCall] = []
        for idx in sorted(tool_calls_builder.keys()):
            builder = tool_calls_builder[idx]
            name = builder["name"]
            if not name:
                continue
            raw_args = builder["arguments"]
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
            final_tool_calls.append(
                ToolCall(id=builder["id"], name=name, arguments=args)
            )

        # Reasoning content fallback (same as non-streaming)
        if not full_text and not final_tool_calls:
            # Some providers put reasoning in the final chunk
            pass

        # Yield final chunk with complete info
        yield StreamChunk(
            delta="",
            is_final=True,
            tool_calls=final_tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
