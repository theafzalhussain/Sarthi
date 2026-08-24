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


class ModelUnavailableError(BrainError):
    """
    Ye model AB CHALEGA HI NAHI — dobara try karna bekaar hai.

    Kab: model deprecate ho gaya (404), key galat hai (401), ya
    provider ne model enable hi nahi kiya (400 pricing/config error).

    Ye alag exception isliye hai ki Brain aise provider ko SESSION KE
    LIYE disable kar de. Warna har message pe wahi dead provider
    pehle try hota hai, fail hota hai, aur user ko 2-3 second extra
    intezaar karna padta hai — har baar.
    """


class RateLimitError(BrainError):
    """
    Free tier ki limit khatam — thodi der baad chal jaayega.

    Ye TEMPORARY hai, isliye provider ko permanently disable nahi
    karte, sirf kuch der ke liye cooldown pe daal dete hain.
    """


def classify_http_error(provider: str, status: int, body: str) -> BrainError:
    """
    HTTP status + response body dekh ke sahi exception banao.

    Ek jagah rakha hai taaki saare providers (OpenAI-compatible aur
    Gemini) same tareeke se behave karein.
    """
    snippet = (body or "")[:300]
    lowered = (body or "").lower()

    if status == 429:
        return RateLimitError(
            f"{provider}: free tier limit khatam ho gayi. "
            f"Thodi der baad try kar — abhi doosra provider use karunga."
        )

    if status in (401, 403):
        return ModelUnavailableError(
            f"{provider}: API key galat ya expire ho gayi hai. "
            f".env file check kar."
        )

    if status == 404:
        return ModelUnavailableError(
            f"{provider}: model nahi mila — shayad deprecate ho gaya.\n"
            f"  Fix: CLI mein '/models' chala, available models dikhenge.\n"
            f"  Phir .env mein {provider.upper()}_MODEL update kar de.\n"
            f"  (server ne kaha: {snippet})"
        )

    # 400 — yahan do tarah ki cheezein aati hain:
    #   (a) model hi available/enabled nahi hai  -> permanent
    #   (b) hamare request mein kuch galat hai   -> temporary
    #
    # (a) ka asli example: Bluesminds pe glm-5.2 ne diya tha
    #     "Model glm-5.2 has not been priced by the administrator yet"
    #     Ye har baar aayega, isliye provider ko disable karna sahi hai.
    if status == 400:
        model_problems = (
            "model_price_error", "has not been priced", "model_not_found",
            "does not exist", "not available", "unsupported model",
            "invalid model", "no such model", "model is not",
            "尚未由管理员配置",  # wahi pricing error, Chinese mein
        )
        if any(hint in lowered for hint in model_problems):
            return ModelUnavailableError(
                f"{provider}: ye model is provider pe enable nahi hai.\n"
                f"  Fix: '/models' chala ke doosra model chun, ya .env mein\n"
                f"  {provider.upper()}_MODEL badal de.\n"
                f"  (server ne kaha: {snippet})"
            )

    return BrainError(f"{provider}: HTTP {status} — {snippet}")
