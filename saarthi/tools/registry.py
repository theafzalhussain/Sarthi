"""
Tool Registry — saare tools ek jagah.

Kaam:
  - Tools register karna
  - LLM ke liye schemas dena
  - Tool ko naam se chalana (validation + safety ke saath)

Yahi jagah hai jahan risky kaam roka jaata hai. Har tool call
isi se guzarta hai — koi bypass nahi.
"""

from __future__ import annotations

import logging
from typing import Any

from ..brain.types import ToolCall, ToolSchema
from ..devices.base import ActionResult
from .base import Tool, ToolContext

log = logging.getLogger("saarthi.tools")


class ToolRegistry:
    """Tools ka collection + safe executor."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------
    #  Registration
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Ek tool add karo."""
        if tool.name in self._tools:
            log.warning("Tool '%s' already registered — replace kar raha hun", tool.name)
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    #  Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    # ------------------------------------------------------------------
    #  Schemas for the LLM
    # ------------------------------------------------------------------

    def schemas(self, available_only_for: ToolContext | None = None) -> list[ToolSchema]:
        """
        LLM ko bhejne wale schemas.

        Agar context diya hai to sirf wahi tools bhejte hain jo abhi
        chal sakte hain. Isse do fayde:
          1. LLM aise tool nahi chunega jo fail hoga
          2. Free tier ke tokens bachte hain (chhota prompt)
        """
        tools = list(self._tools.values())

        if available_only_for is not None:
            tools = [t for t in tools if self._is_usable(t, available_only_for)]

        return [t.schema() for t in tools]

    def _is_usable(self, tool: Tool, ctx: ToolContext) -> bool:
        """Ye tool abhi chal sakta hai?"""
        if tool.requires_capability is None:
            return True

        # Koi bhi device ye capability rakhta hai?
        return len(ctx.devices.with_capability(tool.requires_capability)) > 0

    def describe(self) -> str:
        """Human-readable list — CLI mein dikhane ke liye."""
        if not self._tools:
            return "  (koi tool nahi)"

        lines: list[str] = []
        for name in self.names:
            tool = self._tools[name]
            mark = " [RISKY]" if tool.risky else ""
            lines.append(f"  {name}{mark}")
            lines.append(f"      {tool.description}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  Execution — yahan safety enforce hoti hai
    # ------------------------------------------------------------------

    async def execute(
        self,
        call: ToolCall,
        ctx: ToolContext,
    ) -> ActionResult:
        """
        Tool call chalao — validation aur confirmation ke saath.

        Kabhi exception nahi throw karta. Agent ko hamesha
        structured result milta hai.
        """
        tool = self.get(call.name)

        if tool is None:
            return ActionResult.failure(
                f"'{call.name}' naam ka koi tool nahi hai. "
                f"Available: {', '.join(self.names)}"
            )

        # 1. Arguments check
        problem = tool.validate_args(call.arguments)
        if problem:
            return ActionResult.failure(f"{tool.name}: {problem}")

        # 2. Types theek karo — LLM aur skill placeholders galat type
        #    bhej dete hain ("500" vs 500). Isse crash nahi hota.
        arguments = tool.coerce_args(call.arguments)

        # 3. Safety gate — risky tool pe confirmation
        if tool.risky and ctx.settings.confirm_risky:
            approved = await ctx.ask_confirmation(
                f"{tool.name} chalana hai",
                dict(arguments),
            )
            if not approved:
                return ActionResult.failure(
                    "User ne mana kar diya. Ye kaam nahi kiya."
                )

        # 4. Chalao
        try:
            log.debug("Tool chal raha hai: %s", call)
            result = await tool.run(ctx, **arguments)

            # Tool ne galti se kuch aur return kiya
            if not isinstance(result, ActionResult):
                return ActionResult.success(str(result))

            return result

        except TypeError as exc:
            # Galat arguments — LLM ko samjhao
            return ActionResult.failure(
                f"{tool.name}: arguments galat hain — {exc}"
            )
        except Exception as exc:  # noqa: BLE001 — agent kabhi crash nahi hona chahiye
            log.exception("Tool '%s' crash hua", tool.name)
            return ActionResult.failure(f"{tool.name} crash hua: {exc}")
