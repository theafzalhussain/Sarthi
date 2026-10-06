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
import time
from typing import Any

from ..brain.types import ToolCall, ToolSchema
from ..devices.base import ActionResult
from ..security.permissions import PermissionMode
from ..verification import VerificationStatus
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
        started = time.monotonic()
        tool = self.get(call.name)
        approved: bool | None = None

        def finish(result: ActionResult, status: str | None = None) -> ActionResult:
            """Result ko audit karo; journal ki problem action ko kabhi na tode."""
            audit = getattr(ctx, "audit", None)
            if audit is not None:
                try:
                    message = result.output if result.ok else result.error
                    audit.record(
                        tool=call.name,
                        status=status or ("success" if result.ok else "failed"),
                        arguments=call.arguments,
                        message=message or "",
                        risky=bool(tool and tool.risky),
                        approved=approved,
                        duration_ms=round((time.monotonic() - started) * 1000),
                        session_id=str(ctx.scratch.get("session_id", "")),
                        call_id=str(call.id or ""),
                    )
                except Exception:  # noqa: BLE001 — audit is best effort
                    log.exception("Tool audit write fail: %s", call.name)
            return result

        if tool is None:
            return finish(ActionResult.failure(
                f"'{call.name}' naam ka koi tool nahi hai. "
                f"Available: {', '.join(self.names)}"
            ))

        # 1. Arguments check
        problem = tool.validate_args(call.arguments)
        if problem:
            return finish(ActionResult.failure(f"{tool.name}: {problem}"), "invalid")

        # 2. Granular permission gate — tool > category > default.
        # Hard safety blocks tool ke andar alag hain; ALLOW unhe bypass nahi karta.
        permission_mode = PermissionMode.INHERIT
        permission_source = "built-in"
        if ctx.permissions is not None:
            decision = ctx.permissions.decide(tool.name)
            permission_mode = decision.mode
            permission_source = decision.source
            if permission_mode == PermissionMode.BLOCK:
                return finish(ActionResult.failure(
                    f"'{tool.name}' permission policy se blocked hai "
                    f"({permission_source})."
                ), "permission_blocked")

        # 3. Types theek karo — LLM aur skill placeholders galat type
        #    bhej dete hain ("500" vs 500). Isse crash nahi hota.
        arguments = tool.coerce_args(call.arguments)

        # 4. Confirmation gate. ASK safe tool ko bhi confirmation deta hai;
        # ALLOW sirf confirmation skip karta hai, hard blocks ko nahi.
        needs_confirmation = (
            permission_mode == PermissionMode.ASK
            or (
                permission_mode == PermissionMode.INHERIT
                and tool.risky
                and ctx.settings.confirm_risky
            )
        )
        if needs_confirmation:
            if permission_mode != PermissionMode.ASK and getattr(ctx.settings, "auto_approve", False):
                # FULL ACCESS MODE — user ne khud on kiya hai
                approved = True
                log.info("auto-approve ON — %s bina puche chala raha hun", tool.name)
            else:
                # Is TURN mein isi tool ke liye pehle haan bol diya tha?
                #
                # Kyun: "youtube pe gaana chala aur volume badha" jaisi
                # ek command mein agent 5-6 steps leta hai. Har step pe
                # dobara "haan?" puchna irritating hai aur user blindly
                # haan dabane lagta hai — jo safety ke liye ULTA bura hai.
                #
                # ctx.scratch har turn pe naya banta hai (agent.run_turn
                # ek hi baar _build_context call karta hai), isliye ye
                # approval AGLI command tak nahi jaati.
                approved_tools = ctx.scratch.setdefault("approved_tools", set())

                if tool.name in approved_tools:
                    log.debug(
                        "%s ke liye is turn mein pehle haan bol diya tha",
                        tool.name,
                    )
                else:
                    approved = await ctx.ask_confirmation(
                        f"{tool.name} chalana hai",
                        dict(arguments),
                    )
                    if not approved:
                        return finish(ActionResult.failure(
                            "User ne mana kar diya. Ye kaam nahi kiya."
                        ), "denied")
                    approved_tools.add(tool.name)

        # 4. Chalao
        try:
            log.debug("Tool chal raha hai: %s", call)
            result = await tool.run(ctx, **arguments)

            # Tool ne galti se kuch aur return kiya
            if not isinstance(result, ActionResult):
                result = ActionResult.success(str(result))

            # 5. Outcome verification — execution success ko real-world
            # success assume nahi karte. Evidence tool result data mein aata hai.
            verifier = getattr(ctx, "verifier", None)
            if verifier is not None:
                report = verifier.verify(tool.name, result)
                result.data["verification_status"] = report.status.value
                result.data["verification_message"] = report.message

                if verifier.should_fail(report):
                    return finish(ActionResult.failure(
                        f"Action verification failed: {report.message}",
                        verification_status=report.status.value,
                        verification_message=report.message,
                        original_output=result.output,
                    ), "verification_failed")

                if report.status == VerificationStatus.UNVERIFIED:
                    warning = "⚠️ Action accepted, but final outcome could not be independently verified."
                    result.output = f"{result.output}\n{warning}" if result.output else warning
                    return finish(result, "unverified")

                if report.status == VerificationStatus.VERIFIED:
                    return finish(result, "verified")

            return finish(result)

        except TypeError as exc:
            # Galat arguments — LLM ko samjhao
            return finish(ActionResult.failure(
                f"{tool.name}: arguments galat hain — {exc}"
            ), "crashed")
        except Exception as exc:  # noqa: BLE001 — agent kabhi crash nahi hona chahiye
            log.exception("Tool '%s' crash hua", tool.name)
            return finish(ActionResult.failure(f"{tool.name} crash hua: {exc}"), "crashed")
