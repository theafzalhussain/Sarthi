"""
Provider ka base class.

Naya LLM provider add karna hai? Bas is class ko extend kar.
Baaki pura agent waise hi chalta rahega.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ..config import ProviderConfig
from .types import LLMResponse, Message, StreamChunk, ToolSchema


class LLMProvider(ABC):
    """Ek LLM provider ka interface."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def supports_vision(self) -> bool:
        return self.config.supports_vision

    @property
    def supports_tools(self) -> bool:
        """
        Tool calling kar sakta hai?

        SAARTHI ke liye ye sabse zaroori capability hai — bina tools
        ke agent baat kar sakta hai par KAAM nahi kar sakta.
        """
        return getattr(self.config, "supports_tools", True)

    @property
    def extra_body(self) -> dict:
        """Provider-specific extra payload (reasoning on/off waghairah)."""
        return getattr(self.config, "extra_body", None) or {}

    def resolve_max_tokens(self, requested: int) -> int:
        """
        Is provider ka max_tokens.

        `.env` mein `{NAME}_MAX_TOKENS` set ho to WO jeetta hai, warna
        caller ka bheja hua use hota hai.

        Ye reasoning models ke liye zaroori hai: thinking ON hone pe
        reasoning tokens bhi isi budget se khaate hain, to chhota
        budget jawab beech mein kaat deta hai.
        """
        own = getattr(self.config, "max_tokens", None)
        return own if own else requested

    def resolve_top_p(self):
        """Is provider ka top_p (None = payload mein bhejo hi nahi)."""
        return getattr(self.config, "top_p", None)

    async def list_models(self) -> list[str]:
        """
        Is provider pe kaunse models available hain — LIVE pata karo.

        Ye bahut kaam ka hai kyunki model naam badalte rehte hain.
        Jab 404 "model_not_found" aaye, to isse pata chalega ki ab
        kaunsa naam use karna hai.

        Subclass override kare. Default: khali list.
        """
        return []

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        LLM se baat karo (non-streaming, pura jawab ek baar mein).

        Args:
            messages: Conversation history
            tools: Kaunse tools available hain
            temperature: Kitna creative (0 = fixed, 1 = creative)
            max_tokens: Max jawab ki length

        Returns:
            LLMResponse — text aur/ya tool calls
        """
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamChunk]:
        """
        LLM se baat karo — STREAMING (token by token).

        Real-time output ke liye. Har chunk mein thoda text aata hai,
        user ko turant dikhna shuru hota hai. Last chunk `is_final=True`
        hota hai aur usme complete tool_calls + usage hota hai.

        Default implementation: non-streaming chat() call ke result ko
        ek single chunk mein wrap kar deta hai. Subclass override kare
        actual streaming ke liye.
        """
        # Fallback — providers jo stream nahi karte, unke liye ye chalta hai
        response = await self.chat(messages, tools, temperature, max_tokens)
        chunk = StreamChunk(
            delta=response.text,
            is_final=True,
            tool_calls=response.tool_calls,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )
        yield chunk

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} model={self.model!r}>"
