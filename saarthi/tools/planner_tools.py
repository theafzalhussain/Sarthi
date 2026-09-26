"""
Planner tools — bade kaam ka plan + step-by-step execution.

Pure logic saarthi/planner.py mein hai; yahan sirf tools hain.
(System prompt PLANNING_RULES LLM ko plan_banao ki taraf point karta hai.)
"""

from __future__ import annotations

import logging

from .base import Tool, ToolContext
from ..devices.base import ActionResult
from ..planner import PlanTracker, make_plan

log = logging.getLogger("saarthi.tools.planner")


class PlanBanaoTool(Tool):
    """
    Bade kaam ka plan banao — LLM steps submit karta hai.

    System prompt iski taraf ishara karta hai (complex tasks pe).
    """

    name = "plan_banao"
    description = (
        "Create a step-by-step plan for a complex multi-part task. "
        "Call this FIRST for big tasks, then execute each step with other "
        "tools, calling plan_update after each step. Keep 2-8 small steps."
    )
    parameters = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Poora goal ek line mein"},
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Chhote steps (2-8), order mein",
            },
        },
        "required": ["goal", "steps"],
    }

    async def run(self, ctx: ToolContext, goal: str, steps: list[str]) -> ActionResult:
        plan = make_plan(goal, steps or [])
        if not plan.steps:
            return ActionResult.failure("Steps khaali hain — kam se kam 1 step do.")

        tracker = PlanTracker(plan)
        ctx.scratch["plan_tracker"] = tracker

        return ActionResult.success(
            "Plan ban gaya. Ab EK EK step execute karo (apne tools se) aur "
            "har step ke baad plan_update call karo:\n" + tracker.format()
        )


class PlanUpdateTool(Tool):
    """Step tick karo (done/failed/skip) — progress update."""

    name = "plan_update"
    description = (
        "Update a plan step's status after executing it: 'done', 'failed', "
        "or 'skip'. Call this after EACH step of the active plan."
    )
    parameters = {
        "type": "object",
        "properties": {
            "step_no": {"type": "integer", "description": "Step number (1-based)"},
            "status": {
                "type": "string",
                "enum": ["done", "failed", "skip"],
                "description": "Step ka natija",
            },
            "note": {"type": "string", "description": "Chhota result note (optional)"},
        },
        "required": ["step_no", "status"],
    }

    async def run(
        self, ctx: ToolContext, step_no: int, status: str, note: str = ""
    ) -> ActionResult:
        tracker: PlanTracker | None = ctx.scratch.get("plan_tracker")
        if tracker is None:
            return ActionResult.failure("Koi active plan nahi — pehle plan_banao chalao.")

        step = tracker.update(int(step_no), status)
        if step is None:
            return ActionResult.failure(
                f"Step #{step_no}/{len(tracker.plan.steps)} ya status galat."
            )

        if note:
            tracker.notes.append(f"step {step_no}: {note}")

        tail = "" if tracker.plan.is_finished else " Continue with next step."
        return ActionResult.success(
            f"Step {step_no} -> {step.status}. {tracker.summary()}{tail}\n"
            + tracker.format()
        )


class PlanDikhaoTool(Tool):
    """Chalu plan aur progress dikhao."""

    name = "plan_dikhao"
    description = (
        "Show the current plan and its progress. "
        "Use when user asks 'plan kya hai' / 'kya chal raha hai'."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        tracker: PlanTracker | None = ctx.scratch.get("plan_tracker")
        if tracker is None:
            return ActionResult.success("Abhi koi plan chal nahi raha.")
        return ActionResult.success(
            tracker.format() + "\n" + tracker.summary()
        )


def planner_tools() -> list[Tool]:
    return [PlanBanaoTool(), PlanUpdateTool(), PlanDikhaoTool()]
