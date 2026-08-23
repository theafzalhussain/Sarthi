"""
Brain ke common data types.

Har provider (Groq / Gemini / OpenRouter) inhi types mein baat karega.
Isse agent ko farak nahi padta ki andar kaunsa LLM chal raha hai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    """Message kisne bheja."""

    SYSTEM = "system"      # Agent ko instructions
    USER = "user"          # Tu
    ASSISTANT = "assistant"  # Agent
    TOOL = "tool"          # Tool ka result


@dataclass
class Message:
    """Ek conversation message."""

    role: Role
    content: str

    # Agar assistant ne tool call kiya ho
    tool_calls: list["ToolCall"] = field(default_factory=list)

    # Agar ye TOOL role ka message hai, kis call ka jawab hai
    tool_call_id: str | None = None

    # Optional image (screenshot) — base64 encoded
    image_b64: str | None = None
    image_mime: str = "image/png"

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str, image_b64: str | None = None) -> "Message":
        return cls(role=Role.USER, content=content, image_b64=image_b64)

    @classmethod
    def assistant(
        cls, content: str, tool_calls: list["ToolCall"] | None = None
    ) -> "Message":
        return cls(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tool_calls or [],
        )

    @classmethod
    def tool_result(cls, content: str, tool_call_id: str) -> "Message":
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id)

    @property
    def has_image(self) -> bool:
        return self.image_b64 is not None


@dataclass
class ToolCall:
    """LLM ne bola: ye tool chalao, ye arguments ke saath."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"{self.name}({args})"


@dataclass
class LLMResponse:
    """
    LLM ka jawab.

    text khali ho sakta hai — jab LLM sirf tool chalana chahta hai
    aur kuch bolna nahi chahta. Isliye default "" rakha hai.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    # Debugging ke liye — kaunse provider/model ne jawab diya
    provider: str = ""
    model: str = ""

    # Token usage (free tier limit track karne ke liye kaam aayega)
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        """LLM koi tool chalana chahta hai?"""
        return len(self.tool_calls) > 0


@dataclass
class ToolSchema:
    """Tool ka description jo LLM ko bheja jaata hai."""

    name: str
    description: str
    # JSON Schema format mein parameters
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def to_openai_format(self) -> dict[str, Any]:
        """Groq / OpenRouter ke liye format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_gemini_format(self) -> dict[str, Any]:
        """Gemini ke liye format (thoda alag hai)."""
        params = dict(self.parameters)
        # Gemini ko empty properties pasand nahi
        if not params.get("properties"):
            return {"name": self.name, "description": self.description}
        return {
            "name": self.name,
            "description": self.description,
            "parameters": params,
        }


class BrainError(Exception):
    """Brain layer ki koi bhi problem."""


class NoProviderError(BrainError):
    """Koi LLM provider available nahi (API key nahi hai)."""


class AllProvidersFailedError(BrainError):
    """Saare providers try kiye, sab fail ho gaye."""
