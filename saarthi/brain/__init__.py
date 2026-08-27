"""
SAARTHI Brain — LLM layer.

Ek hi interface, andar teen providers (Groq / Gemini / OpenRouter).
Agent ko farak nahi padta kaunsa chal raha hai.

Use:
    from saarthi.brain import Brain, Message

    brain = Brain()
    reply = await brain.ask("Namaste, kaise ho?")
"""

from .base import LLMProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider
from .router import Brain
from .types import (
    AllProvidersFailedError,
    BrainError,
    LLMResponse,
    Message,
    NoProviderError,
    Role,
    StreamChunk,
    ToolCall,
    ToolSchema,
)

__all__ = [
    "Brain",
    "LLMProvider",
    "GeminiProvider",
    "OpenAICompatProvider",
    "Message",
    "Role",
    "ToolCall",
    "ToolSchema",
    "LLMResponse",
    "StreamChunk",
    "BrainError",
    "NoProviderError",
    "AllProvidersFailedError",
]
