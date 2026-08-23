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
