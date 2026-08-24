"""
Provider ka base class.

Naya LLM provider add karna hai? Bas is class ko extend kar.
Baaki pura agent waise hi chalta rahega.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import ProviderConfig
from .types import LLMResponse, Message, ToolSchema


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
        LLM se baat karo.

        Args:
            messages: Conversation history
            tools: Kaunse tools available hain
            temperature: Kitna creative (0 = fixed, 1 = creative)
            max_tokens: Max jawab ki length

        Returns:
            LLMResponse — text aur/ya tool calls
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} model={self.model!r}>"
