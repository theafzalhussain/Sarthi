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
from ..task_engine import DurableTaskStore, format_task

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

        # Durable checkpoint: process crash/restart par bhi plan nahi khoyega.
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        if store is not None:
            try:
                task = store.create(
                    plan.goal, [step.action for step in plan.steps],
                    session_id=str(ctx.scratch.get("session_id", "")),
                )
                ctx.scratch["active_task_id"] = task.id
                return ActionResult.success(
                    "Durable plan ban gaya. Har step ke baad plan_update call karo. "
                    "Crash/restart hua to isi checkpoint se resume hoga:\n" + format_task(task),
                    task_id=task.id,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Durable plan save fail, memory fallback: %s", exc)

        return ActionResult.success(
            "Plan ban gaya (memory-only fallback). Ab EK EK step execute karo aur "
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
        # Persistent store first: active id current turn se, warna latest
        # paused/running task DB se. Isliye nayi process mein bhi update hota hai.
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        if store is not None:
            task_id = ctx.scratch.get("active_task_id")
            task = store.get(task_id) if task_id else store.latest_active()
            if task is not None:
                try:
                    updated = store.update_step(task.id, int(step_no), status, note)
                    ctx.scratch["active_task_id"] = task.id
                    return ActionResult.success(format_task(updated), task_id=task.id)
                except (ValueError, IndexError) as exc:
                    return ActionResult.failure(f"Plan update galat hai: {exc}")

        tracker: PlanTracker | None = ctx.scratch.get("plan_tracker")
        if tracker is None:
            return ActionResult.failure("Koi active plan nahi — pehle plan_banao chalao.")
        step = tracker.update(int(step_no), status)
        if step is None:
            return ActionResult.failure(f"Step #{step_no}/{len(tracker.plan.steps)} ya status galat.")
        if note:
            tracker.notes.append(f"step {step_no}: {note}")
        tail = "" if tracker.plan.is_finished else " Continue with next step."
        return ActionResult.success(
            f"Step {step_no} -> {step.status}. {tracker.summary()}{tail}\n" + tracker.format()
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
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        if store is not None:
            task_id = ctx.scratch.get("active_task_id")
            task = store.get(task_id) if task_id else store.latest_active()
            if task is not None:
                return ActionResult.success(format_task(task), task_id=task.id)
        tracker: PlanTracker | None = ctx.scratch.get("plan_tracker")
        if tracker is None:
            return ActionResult.success("Abhi koi plan chal nahi raha.")
        return ActionResult.success(tracker.format() + "\n" + tracker.summary())


class TaskResumeTool(Tool):
    name = "task_resume_karo"
    description = "Resume a paused durable task after a restart/failure, from its saved checkpoint."
    parameters = {
        "type": "object",
        "properties": {"task_id": {"type": "string", "description": "Task ID; blank means latest paused task"}},
    }
    risky = True

    async def run(self, ctx: ToolContext, task_id: str = "") -> ActionResult:
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        if store is None:
            return ActionResult.failure("Durable task engine available nahi hai.")
        task = store.get(task_id) if task_id else store.latest_active()
        if task is None:
            return ActionResult.failure("Koi paused/active durable task nahi mila.")
        if task.status in {"completed", "cancelled"}:
            return ActionResult.failure(f"Task already {task.status} hai.")
        updated = store.set_status(task.id, "running")
        ctx.scratch["active_task_id"] = task.id
        return ActionResult.success(
            "Checkpoint load ho gaya. Pending step se continue karo:\n" + format_task(updated),
            task_id=task.id,
        )


class TaskPauseTool(Tool):
    name = "task_pause_karo"
    description = "Pause the current durable task safely; checkpoints remain saved for later resume."
    parameters = {"type": "object", "properties": {"reason": {"type": "string"}}}

    async def run(self, ctx: ToolContext, reason: str = "User requested pause") -> ActionResult:
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        task = store.latest_active() if store else None
        if task is None:
            return ActionResult.failure("Koi active task nahi mila.")
        updated = store.set_status(task.id, "paused", reason)
        return ActionResult.success(format_task(updated), task_id=task.id)


class TasksListTool(Tool):
    name = "tasks_dikhao"
    description = "List recent durable tasks and their status/progress."
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        store: DurableTaskStore | None = ctx.scratch.get("task_store")
        tasks = store.list(10) if store else []
        if not tasks:
            return ActionResult.success("Abhi koi durable task nahi hai.")
        lines = []
        for task in tasks:
            done, total = task.progress
            lines.append(f"{task.id} · {task.status} · {done}/{total} · {task.goal}")
        return ActionResult.success("Recent tasks:\n" + "\n".join(lines))


def planner_tools() -> list[Tool]:
    return [
        PlanBanaoTool(), PlanUpdateTool(), PlanDikhaoTool(),
        TaskResumeTool(), TaskPauseTool(), TasksListTool(),
    ]
