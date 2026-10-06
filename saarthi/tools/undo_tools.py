"""User-facing safe rollback tools."""
from __future__ import annotations

from ..devices.base import ActionResult
from .base import Tool, ToolContext


class UndoTool(Tool):
    name = "undo_karo"
    description = (
        "Undo the latest reversible JARVIS action, or a specific undo token. "
        "Currently supports file create/overwrite/append. Never overwrites later user edits."
    )
    parameters = {
        "type": "object",
        "properties": {"token": {"type": "string", "description": "Optional undo token"}},
    }
    risky = True

    async def run(self, ctx: ToolContext, token: str = "") -> ActionResult:
        if ctx.rollback is None:
            return ActionResult.failure("Undo system available nahi hai.")
        try:
            entry = ctx.rollback.undo(token.strip())
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            return ActionResult.failure(f"Safe undo nahi hua: {exc}")
        return ActionResult.success(
            f"Undo complete: {entry.description}",
            verified=True,
            verification_message="Original file state safely restore hui",
            undo_token=entry.token,
        )


class UndoListTool(Tool):
    name = "undo_dikhao"
    description = "Show recent actions that JARVIS can safely undo."
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        entries = ctx.rollback.list_ready(20) if ctx.rollback is not None else []
        if not entries:
            return ActionResult.success("Abhi koi reversible action pending nahi hai.")
        lines = [f"{e.token} · {e.description}" for e in entries]
        return ActionResult.success("Undo available:\n" + "\n".join(lines))


def undo_tools() -> list[Tool]:
    return [UndoTool(), UndoListTool()]
