"""
Tool abstraction — agent ke "haath".

Design:
    Tool = ek kaam jo agent kar sakta hai.
    Har tool apna naam, description aur parameters declare karta hai.
    LLM ko ye schema jaata hai, wo decide karta hai kaunsa chalana hai.

Naya tool add karna bahut aasaan hai — Tool extend kar aur register kar.
Agent ka loop badalna nahi padta. Isi tarah "full laundry" banti hai:
jitne tools add karega, utna capable agent hoga.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..brain.types import ToolSchema
from ..devices.base import ActionResult

if TYPE_CHECKING:
    from ..config import Settings
    from ..devices.manager import DeviceManager
    from ..memory.store import MemoryStore
    from ..skills.store import SkillStore


# Confirmation callback ka type:
#   (kya karne wala hai, details) -> haan/nahi
ConfirmFn = Callable[[str, dict], Awaitable[bool]]


@dataclass
class ToolContext:
    """
    Tools ko jo cheezein chahiye — sab ek jagah.

    Isse tools loosely coupled rehte hain: unhe agent ka pura object
    nahi chahiye, sirf ye context.
    """

    devices: "DeviceManager"
    settings: "Settings"

    # Confirmation lene ka tareeka (risky kaam ke liye)
    confirm: ConfirmFn | None = None

    # Memory aur skills — Task #6 mein aa rahe hain
    memory: "MemoryStore | None" = None
    skills: "SkillStore | None" = None

    # Agent ka current conversation context (tools padh sakte hain)
    scratch: dict[str, Any] = field(default_factory=dict)

    async def ask_confirmation(self, action: str, details: dict | None = None) -> bool:
        """
        User se permission maango.

        Agar confirm callback set nahi hai to SAFE default: mana kar do.
        Fail-safe design — chup-chaap risky kaam nahi hona chahiye.
        """
        if self.confirm is None:
            return False
        return await self.confirm(action, details or {})


class Tool(ABC):
    """
    Ek tool jo agent chala sakta hai.

    Subclass mein set karo:
        name        -> LLM isi naam se bulayega
        description -> LLM isse samajhta hai kab use karna hai
        parameters  -> JSON Schema
        risky       -> True ho to confirmation liya jaayega
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    # Risky tools pe user se pucha jaayega
    risky: bool = False

    # Kaunse capability ki zarurat hai (None = koi device nahi chahiye)
    requires_capability: Any = None

    def __init__(self) -> None:
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} ka 'name' set nahi hai")
        if not self.description:
            raise ValueError(f"{self.name} ka 'description' set nahi hai")

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs: Any) -> ActionResult:
        """
        Tool chalao.

        Exception throw MAT karo — ActionResult.failure() return karo.
        Agent ko structured error chahiye taaki wo recover kar sake.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    #  Schema
    # ------------------------------------------------------------------

    def schema(self) -> ToolSchema:
        """LLM ko bhejne wala schema."""
        description = self.description
        if self.risky:
            description += " (RISKY — pehle user se confirmation liya jaayega)"

        return ToolSchema(
            name=self.name,
            description=description,
            parameters=self.parameters,
        )

    def required_params(self) -> list[str]:
        """Kaunse parameters zaroori hain."""
        return list(self.parameters.get("required", []))

    def validate_args(self, args: dict[str, Any]) -> str | None:
        """
        Arguments check karo. Problem ho to message return karo.

        LLM kabhi kabhi parameter bhool jaata hai — clear error dene se
        wo agli koshish mein sahi kar leta hai.
        """
        missing = [p for p in self.required_params() if p not in args]
        if missing:
            return f"Ye parameters missing hain: {', '.join(missing)}"

        allowed = set(self.parameters.get("properties", {}))
        if allowed:
            unknown = [k for k in args if k not in allowed]
            if unknown:
                return (
                    f"Ye parameters samajh nahi aaye: {', '.join(unknown)}. "
                    f"Allowed: {', '.join(sorted(allowed))}"
                )
        return None

    def coerce_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Arguments ko schema ke hisaab se sahi type mein badlo.

        Ye zaroori hai kyunki do jagah se galat type aata hai:

          1. LLM: "500" (string) bhejta hai jahan 500 (number) chahiye.
             Ye bahut common hai, khaaskar chhote models mein.

          2. Skills: {amount} placeholder resolve hoke 1240 (int) ban
             jaata hai, par tool ko "1240" (string) chahiye.

        Isse crash nahi hota aur tools simple rehte hain.
        """
        properties = self.parameters.get("properties", {})
        if not properties:
            return dict(args)

        coerced: dict[str, Any] = {}

        for key, value in args.items():
            spec = properties.get(key)
            if not isinstance(spec, dict) or value is None:
                coerced[key] = value
                continue

            expected = spec.get("type")

            try:
                if expected == "string" and not isinstance(value, str):
                    coerced[key] = str(value)

                elif expected == "integer" and not isinstance(value, int):
                    # bool bhi int hai — usko chhodo
                    coerced[key] = int(float(str(value).strip()))

                elif expected == "number" and not isinstance(value, (int, float)):
                    coerced[key] = float(str(value).strip())

                elif expected == "boolean" and not isinstance(value, bool):
                    coerced[key] = str(value).strip().lower() in {
                        "1", "true", "yes", "haan", "y", "on",
                    }

                else:
                    coerced[key] = value

            except (TypeError, ValueError):
                # Convert nahi hua to jaisa hai waisa bhej do —
                # tool khud clear error dega
                coerced[key] = value

        return coerced

    def __repr__(self) -> str:
        return f"<Tool {self.name}{' [risky]' if self.risky else ''}>"


# ----------------------------------------------------------------------
#  Chhote tools jaldi banane ke liye helper
# ----------------------------------------------------------------------


def simple_tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    risky: bool = False,
):
    """
    Decorator — ek function ko tool bana do.

    Use:
        @simple_tool("time_bata", "Abhi ka time batao")
        async def time_tool(ctx):
            return ActionResult.success(str(datetime.now()))
    """

    def decorator(func: Callable[..., Awaitable[ActionResult]]) -> Tool:
        class _FunctionTool(Tool):
            pass

        _FunctionTool.name = name
        _FunctionTool.description = description
        _FunctionTool.parameters = parameters or {
            "type": "object",
            "properties": {},
        }
        _FunctionTool.risky = risky

        async def run(self, ctx: ToolContext, **kwargs: Any) -> ActionResult:
            return await func(ctx, **kwargs)

        _FunctionTool.run = run  # type: ignore[assignment]
        _FunctionTool.__name__ = f"Tool_{name}"

        return _FunctionTool()

    return decorator
