"""
Brain — SAARTHI ka dimaag.

Ye class providers ko manage karti hai:
  - Groq pehle try karta hai (sabse fast, sabse zyada free limit)
  - Fail ho to OpenRouter
  - Screenshot dekhna hai to Gemini (kyunki usi ke paas aankh hai)

Free tier pe rate limit aana normal hai. Isliye fallback zaroori hai —
ek provider thak jaaye to agent ruke nahi, doosre se kaam chalaye.
"""

from __future__ import annotations

import logging

from ..config import Settings, settings as default_settings
from .base import LLMProvider
from .gemini import GeminiProvider
from .openai_compat import BASE_URLS, OpenAICompatProvider
from .types import (
    AllProvidersFailedError,
    BrainError,
    LLMResponse,
    Message,
    NoProviderError,
    ToolSchema,
)

log = logging.getLogger("saarthi.brain")


def _build_provider(config) -> LLMProvider | None:
    """
    Config se sahi provider class banao.

    Gemini ka API alag hai (usko apni class chahiye). Baaki sab
    OpenAI-compatible hain — ek hi class se chal jaate hain.
    """
    if config.name == "gemini":
        return GeminiProvider(config)

    # OpenAI-compatible: groq, openrouter, nvidia
    if config.name in BASE_URLS:
        return OpenAICompatProvider(config)

    log.warning(
        "Unknown provider '%s'. OpenAI-compatible hai? To openai_compat.py "
        "ke BASE_URLS mein URL daal de.",
        config.name,
    )
    return None


class Brain:
    """Multi-provider LLM brain with automatic fallback."""

    def __init__(self, config: Settings | None = None):
        self.settings = config or default_settings
        self.providers: list[LLMProvider] = []

        for provider_config in self.settings.available_providers:
            provider = _build_provider(provider_config)
            if provider:
                self.providers.append(provider)

        # Config wale order mein sort karo (.env se badal sakta hai)
        order = self.settings.provider_order
        self.providers.sort(
            key=lambda p: order.index(p.name) if p.name in order else 99
        )

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Koi provider available hai?"""
        return len(self.providers) > 0

    @property
    def has_vision(self) -> bool:
        """Screenshot samajh sakta hai?"""
        return any(p.supports_vision for p in self.providers)

    @property
    def has_tools(self) -> bool:
        """
        Koi provider tools chala sakta hai?

        Ye check zaroori hai — bina tool calling ke SAARTHI sirf
        chatbot hai, agent nahi.
        """
        return any(p.supports_tools for p in self.providers)

    def status(self) -> str:
        """Human-readable status — CLI mein dikhane ke liye."""
        if not self.providers:
            return "Koi provider nahi (API key daal .env mein)"

        lines = []
        for i, p in enumerate(self.providers):
            tag = "primary" if i == 0 else "fallback"
            marks = []
            if p.supports_vision:
                marks.append("aankh: screenshot dekh sakta hai")
            if not p.supports_tools:
                marks.append("tools NAHI — sirf baat kar sakta hai")
            extra = f" [{'; '.join(marks)}]" if marks else ""
            lines.append(f"  {p.name:<12} {p.model:<40} ({tag}){extra}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  Main entry point
    # ------------------------------------------------------------------

    async def think(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        need_vision: bool = False,
    ) -> LLMResponse:
        """
        Sochne ka kaam. Provider fail ho to agla try karega.

        Args:
            messages: Conversation
            tools: Available tools
            temperature: Creativity
            max_tokens: Jawab ki max length
            need_vision: Screenshot samajhna hai? (to sirf vision providers)

        Raises:
            NoProviderError: Koi provider hi nahi hai
            AllProvidersFailedError: Sab try kiye, sab fail
        """
        if not self.providers:
            raise NoProviderError(self.settings.setup_help())

        # Kaunse providers use kar sakte hain
        candidates = self.providers
        if need_vision:
            candidates = [p for p in self.providers if p.supports_vision]
            if not candidates:
                raise NoProviderError(
                    "Screenshot samajhne ke liye Gemini key chahiye.\n"
                    "Free key: https://aistudio.google.com/apikey\n"
                    "Phir .env mein GEMINI_API_KEY daal de."
                )

        # Agar messages mein image hai, to non-vision provider bekaar hai
        if any(m.has_image for m in messages):
            vision_only = [p for p in candidates if p.supports_vision]
            if vision_only:
                candidates = vision_only

        # Tools chahiye? To pehle un providers ko try karo jo tools
        # SUPPORT karte hain.
        #
        # Kyun ye zaroori hai: kuch models (jaise diffusion wale) tools
        # ko chup-chaap IGNORE kar dete hain. Phir wo bas text bhej dete
        # hain, agent ka loop khatam ho jaata hai, aur user ko lagta hai
        # "agent ne kaam kiya hi nahi". Silent failure sabse buri cheez
        # hai — isliye aise providers ko peeche dhakel dete hain.
        #
        # Poora HATA nahi rahe — agar tool wale saare fail ho jaayein to
        # kuch jawab dena chup rehne se behtar hai.
        if tools:
            with_tools = [p for p in candidates if p.supports_tools]
            without_tools = [p for p in candidates if not p.supports_tools]
            if with_tools:
                candidates = with_tools + without_tools

        errors: list[str] = []

        for provider in candidates:
            try:
                log.debug("Trying provider: %s", provider.name)
                response = await provider.chat(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if self.settings.debug:
                    log.info(
                        "%s ne jawab diya (%d prompt + %d completion tokens)",
                        provider.name,
                        response.prompt_tokens,
                        response.completion_tokens,
                    )
                return response

            except BrainError as exc:
                # Ye provider fail hua — agle pe jao
                log.warning("%s fail hua: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue

            except Exception as exc:  # noqa: BLE001 — unexpected bhi handle karo
                log.warning("%s unexpected error: %s", provider.name, exc)
                errors.append(f"{provider.name}: unexpected — {exc}")
                continue

        raise AllProvidersFailedError(
            "Saare providers fail ho gaye bhai:\n  "
            + "\n  ".join(errors)
        )

    # ------------------------------------------------------------------
    #  Convenience
    # ------------------------------------------------------------------

    async def discover_models(self) -> dict[str, list[str] | str]:
        """
        Har provider se LIVE pata karo ki kaunse models available hain.

        Ye tab kaam aata hai jab "model_not_found" error aaye —
        matlab model deprecate ho gaya. Isse pata chalega ki ab
        kaunsa naam use karna hai.

        Returns:
            {provider_name: [model, ...]} ya {provider_name: "error message"}
        """
        results: dict[str, list[str] | str] = {}

        for provider in self.providers:
            try:
                results[provider.name] = await provider.list_models()
            except Exception as exc:  # noqa: BLE001
                results[provider.name] = f"error: {exc}"

        return results

    async def ask(self, prompt: str, system: str | None = None) -> str:
        """
        Ek simple sawaal, ek simple jawab. Tools nahi.
        Testing aur chhote kaamon ke liye.
        """
        messages: list[Message] = []
        if system:
            messages.append(Message.system(system))
        messages.append(Message.user(prompt))

        response = await self.think(messages)
        return response.text
