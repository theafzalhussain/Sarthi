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
import time
from collections.abc import AsyncIterator

from ..config import Settings, settings as default_settings
from .base import LLMProvider
from .gemini import GeminiProvider
from .openai_compat import BASE_URLS, OpenAICompatProvider
from .types import (
    AllProvidersFailedError,
    BrainError,
    LLMResponse,
    Message,
    ModelUnavailableError,
    NoProviderError,
    RateLimitError,
    StreamChunk,
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

        # ---- PROVIDER HEALTH ----
        #
        # Kyun ye chahiye: user ka bluesminds/glm-5.2 har message pe
        # HTTP 400 de raha tha ("model has not been priced"). Wo error
        # HAR BAAR aayega — par purana code har turn pe usko pehle try
        # karta tha, 1-2 second barbaad karta tha, phir fallback.
        #
        # Ab: dead provider SESSION KE LIYE hat jaata hai, aur rate-limit
        # wala thodi der ke liye. User ko sirf ek baar batate hain.
        self._dead: dict[str, str] = {}        # naam -> wajah (permanent)
        self._cooldown: dict[str, float] = {}  # naam -> kab tak skip karna hai
        self._failures: dict[str, int] = {}     # naam -> lagatar fail count

        # CLI/voice isko set karta hai taaki fallback ki khabar UI mein
        # theek se dikhe. Warna logging ka raw warning stderr pe chhap
        # jaata hai aur look kharab lagta hai.
        self.notify = None

    # ------------------------------------------------------------------
    #  Provider health
    # ------------------------------------------------------------------

    COOLDOWN_SECONDS = 30

    def _say(self, kind: str, text: str) -> None:
        """UI ko batao (agar koi sun raha hai)."""
        if callable(self.notify):
            try:
                self.notify(kind, text)
            except Exception:  # noqa: BLE001 — UI ki galti se agent na ruke
                pass

    def _is_usable(self, provider: LLMProvider) -> bool:
        """Ye provider abhi try karne layak hai?"""
        if provider.name in self._dead:
            return False
        until = self._cooldown.get(provider.name, 0.0)
        if until and time.monotonic() < until:
            return False
        # Cooldown khatam — saaf kar do
        self._cooldown.pop(provider.name, None)
        return True

    # Itni baar lagatar fail hua to cooldown pe daal do.
    #
    # ⚠️ YE EK ASLI PROBLEM SE AAYA HAI.
    #
    # User ka deepseek HAR STEP pe fail ho raha tha:
    #     · deepseek ne kaam nahi kiya, nvidia se kar diya
    #     · deepseek ne kaam nahi kiya, nvidia se kar diya
    #     ... (8 step tak, har baar)
    #
    # Error permanent nahi tha (timeout/network type), isliye
    # mark_dead() nahi lagta tha — aur provider HAR STEP pe dobara try
    # hota tha. Ek YouTube task mein 58 SECOND lag gaye.
    #
    # Ab: koi provider lagatar itni baar fail ho to thodi der ke liye
    # chhod dete hain, chahe error "temporary" ho.
    MAX_CONSECUTIVE_FAILURES = 3

    def _note_failure(self, name: str) -> None:
        """Lagatar fail ka count badhao, aur limit paar ho to cooldown."""
        count = self._failures.get(name, 0) + 1
        self._failures[name] = count

        if count >= self.MAX_CONSECUTIVE_FAILURES:
            self.mark_cooldown(name)
            self._failures[name] = 0
            self._say(
                "debug",
                f"{name} lagatar {count} baar fail hua — "
                f"{self.COOLDOWN_SECONDS}s ke liye chhod raha hun",
            )

    def _note_success(self, name: str) -> None:
        """Chal gaya — counter reset."""
        self._failures.pop(name, None)

    def mark_dead(self, name: str, reason: str) -> None:
        """Ye provider session bhar ke liye band."""
        if name not in self._dead:
            self._dead[name] = reason
            log.warning("%s ko session ke liye hata diya: %s", name, reason)

    def mark_cooldown(self, name: str) -> None:
        """Rate limit — thodi der ke liye chhod do."""
        self._cooldown[name] = time.monotonic() + self.COOLDOWN_SECONDS

    def health(self) -> dict[str, str]:
        """
        Har provider ka haal — UI ke liye.

        Returns: {provider_name: "ok" | "dead: wajah" | "cooldown: 42s"}
        """
        status: dict[str, str] = {}
        now = time.monotonic()
        for provider in self.providers:
            if provider.name in self._dead:
                status[provider.name] = f"dead: {self._dead[provider.name]}"
                continue
            until = self._cooldown.get(provider.name, 0.0)
            if until and now < until:
                status[provider.name] = f"cooldown: {int(until - now)}s"
                continue
            status[provider.name] = "ok"
        return status

    def reset_health(self) -> None:
        """Sab dobara try karo (CLI ka /retry)."""
        self._dead.clear()
        self._cooldown.clear()
        self._failures.clear()

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
        max_tokens: int | None = None,
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

        # Caller ne max_tokens na diya to global setting use karo
        # (SAARTHI_MAX_TOKENS). Provider ka apna override iske BAAD
        # lagta hai — resolve_max_tokens() mein.
        if max_tokens is None:
            max_tokens = getattr(self.settings, "max_tokens", 4096)

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

        # Dead / cooldown wale providers hata do — inko try karna sirf
        # waqt barbaad karna hai
        healthy = [p for p in candidates if self._is_usable(p)]

        # Sab dead? To phir bhi try karo — kuch na karne se behtar hai
        # (ho sakta hai provider ab theek ho gaya ho)
        if not healthy:
            if candidates:
                log.info("Saare providers dead the — dobara try kar raha hun")
                self.reset_health()
                healthy = candidates
            else:
                raise NoProviderError(self.settings.setup_help())

        errors: list[str] = []

        for index, provider in enumerate(healthy):
            try:
                log.debug("Trying provider: %s", provider.name)
                response = await provider.chat(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # Pehla provider fail hua tha par ye chal gaya — user ko
                # bata do, warna usko lagta hai kuch gadbad hai
                if index > 0:
                    self._say(
                        "debug",
                        f"{healthy[0].name} ne kaam nahi kiya, "
                        f"{provider.name} se kar diya",
                    )

                self._note_success(provider.name)

                if self.settings.debug:
                    log.info(
                        "%s ne jawab diya (%d prompt + %d completion tokens)",
                        provider.name,
                        response.prompt_tokens,
                        response.completion_tokens,
                    )
                return response

            except ModelUnavailableError as exc:
                # Ye permanent hai — session bhar ke liye hata do
                short = str(exc).splitlines()[0]
                self.mark_dead(provider.name, short)
                self._say("error", f"{provider.name} hata diya — {short}")
                errors.append(f"{provider.name}: {exc}")
                continue

            except RateLimitError as exc:
                # Temporary — thodi der ke liye chhod do
                self.mark_cooldown(provider.name)
                self._say(
                    "debug",
                    f"{provider.name} ki limit khatam — "
                    f"{self.COOLDOWN_SECONDS}s ke liye chhod raha hun",
                )
                errors.append(f"{provider.name}: {exc}")
                continue

            except BrainError as exc:
                # Ye provider fail hua — agle pe jao.
                # Lagatar fail ho raha hai to cooldown pe daal do,
                # warna HAR STEP pe dobara try hoga aur waqt barbaad.
                log.warning("%s fail hua: %s", provider.name, exc)
                self._note_failure(provider.name)
                errors.append(f"{provider.name}: {exc}")
                continue

            except Exception as exc:  # noqa: BLE001 — unexpected bhi handle karo
                log.warning("%s unexpected error: %s", provider.name, exc)
                self._note_failure(provider.name)
                errors.append(f"{provider.name}: unexpected — {exc}")
                continue

        raise AllProvidersFailedError(
            "Saare providers fail ho gaye bhai:\n  "
            + "\n  ".join(errors)
        )

    # ------------------------------------------------------------------
    #  Streaming — real-time token output
    # ------------------------------------------------------------------

    async def think_stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        need_vision: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """
        Streaming version of think() — tokens jaise aate hain yield karo.

        Same fallback logic as think(): provider fail ho to agla try.
        Par streaming shuru hone ke baad provider switch nahi hota —
        ek baar stream chalu to wahi complete karo.

        Usage:
            full_text = ""
            async for chunk in brain.think_stream(messages, tools):
                if chunk.delta:
                    print(chunk.delta, end="", flush=True)
                    full_text += chunk.delta
                if chunk.is_final:
                    tool_calls = chunk.tool_calls
        """
        if not self.providers:
            raise NoProviderError(self.settings.setup_help())

        if max_tokens is None:
            max_tokens = getattr(self.settings, "max_tokens", 4096)

        # --- Provider selection (same as think()) ---
        candidates = self.providers
        if need_vision:
            candidates = [p for p in self.providers if p.supports_vision]
            if not candidates:
                raise NoProviderError(
                    "Screenshot samajhne ke liye Gemini key chahiye.\n"
                    "Free key: https://aistudio.google.com/apikey\n"
                    "Phir .env mein GEMINI_API_KEY daal de."
                )

        if any(m.has_image for m in messages):
            vision_only = [p for p in candidates if p.supports_vision]
            if vision_only:
                candidates = vision_only

        if tools:
            with_tools = [p for p in candidates if p.supports_tools]
            without_tools = [p for p in candidates if not p.supports_tools]
            if with_tools:
                candidates = with_tools + without_tools

        healthy = [p for p in candidates if self._is_usable(p)]
        if not healthy:
            if candidates:
                self.reset_health()
                healthy = candidates
            else:
                raise NoProviderError(self.settings.setup_help())

        errors: list[str] = []

        for index, provider in enumerate(healthy):
            try:
                log.debug("Streaming from provider: %s", provider.name)

                # Start streaming — ek baar shuru ho to complete karo
                async for chunk in provider.chat_stream(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk

                # Successfully completed
                if index > 0:
                    self._say(
                        "debug",
                        f"{healthy[0].name} ne kaam nahi kiya, "
                        f"{provider.name} se stream kiya",
                    )
                self._note_success(provider.name)
                return  # Stream complete

            except ModelUnavailableError as exc:
                short = str(exc).splitlines()[0]
                self.mark_dead(provider.name, short)
                self._say("error", f"{provider.name} hata diya — {short}")
                errors.append(f"{provider.name}: {exc}")
                continue

            except RateLimitError as exc:
                self.mark_cooldown(provider.name)
                self._say(
                    "debug",
                    f"{provider.name} ki limit khatam — "
                    f"{self.COOLDOWN_SECONDS}s ke liye chhod raha hun",
                )
                errors.append(f"{provider.name}: {exc}")
                continue

            except BrainError as exc:
                log.warning("%s stream fail: %s", provider.name, exc)
                self._note_failure(provider.name)
                errors.append(f"{provider.name}: {exc}")
                continue

            except Exception as exc:  # noqa: BLE001
                log.warning("%s unexpected stream error: %s", provider.name, exc)
                self._note_failure(provider.name)
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
