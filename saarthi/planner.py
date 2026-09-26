"""
Planner — bade kaam ko STEPS mein todna, phir ek-ek karke pura karna.

PROBLEM:

    "Mera poora project setup kar de" jaise kaam mein LLM ek hi turn
    mein sab kuch karne ki koshish karta hai — aadha chhod deta hai,
    ya koi step bhool jaata hai. Human kaise karta hai? PLAN banata
    hai, list ke saamne tick karta hai.

SOLUTION — plan as a TOOL (agent loop ko chhede bina):

    1. `plan_banao`   -> LLM khud steps list banata hai (structured)
    2. har step wo APNE existing tools se execute karta hai
    3. `plan_update`  -> har step ke baad tick/fail — progress dikhta hai
    4. `plan_dikhao`  -> user ko bhi status dikhta hai

    Ye design jaan-boojh ke loop-free hai: agent ka core loop waisa ka
    waisa hai, planner sirf SCAFFOLDING deta hai. (Repo rule: chhota
    samajhne layak code.)

    Tracker pure logic hai — PlanTracker ke bina I/O test hota hai.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# PURE LOGIC module — yahan koi tool/hardware import NAHI.
# (Tools iske upar saarthi/tools/planner_tools.py mein hain —
#  circular import se bachne ke liye direction sirf ek hai:
#  tools -> planner)


# ======================================================================
#  Pure logic
# ======================================================================


@dataclass
class PlanStep:
    """Ek step — chhota, karta hua kaam."""

    action: str
    status: str = "pending"  # pending | done | failed | skipped


@dataclass
class Plan:
    """Poora plan — goal + steps."""

    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def progress(self) -> tuple[int, int]:
        """(done, total) — done mein skipped bhi ginte hain (resolved)."""
        done = sum(1 for s in self.steps if s.status in ("done", "skipped"))
        return done, len(self.steps)

    @property
    def is_finished(self) -> bool:
        return all(s.status in ("done", "failed", "skipped") for s in self.steps)

    def format(self) -> str:
        """Checkboxes wali readable plan (user + LLM dono ke liye)."""
        icon = {"done": "✅", "failed": "❌", "skipped": "⏭️", "pending": "⬜"}
        lines = [f"📋 PLAN: {self.goal}"]
        for i, step in enumerate(self.steps, start=1):
            lines.append(f"  {icon.get(step.status, '⬜')} {i}. {step.action}")
        done, total = self.progress
        lines.append(f"  — {done}/{total} ho gaya —")
        return "\n".join(lines)


def parse_plan_json(text: str) -> Plan | None:
    """
    LLM output se plan nikalo (PURE LOGIC — tested).

    Handles:
      - pure JSON array: ["step1", "step2"]
      - object: {"goal": "...", "steps": [...]}
      - ```json fenced blocks
      - steps as objects: {"action": "..."}
    """
    if not text or not text.strip():
        return None

    candidate = text.strip()

    # Markdown fence hatao
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", candidate)
    if fence:
        candidate = fence.group(1).strip()

    # JSON object/array dhoondo
    data: Any = None
    try:
        data = json.loads(candidate)
    except Exception:  # noqa: BLE001
        # Text ke andar {..} ya [..] dhoondo
        for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
            m = re.search(pattern, candidate)
            if m:
                try:
                    data = json.loads(m.group(0))
                    break
                except Exception:  # noqa: BLE001
                    continue

    if data is None:
        return None

    goal = ""
    raw_steps: Any = None

    if isinstance(data, list):
        raw_steps = data
    elif isinstance(data, dict):
        goal = str(data.get("goal", data.get("title", "")) or "")
        raw_steps = data.get("steps", data.get("plan"))
    else:
        return None

    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    steps: list[PlanStep] = []
    for item in raw_steps[:20]:  # sanbhali kharui — 20 steps se zyada plan nahi
        if isinstance(item, dict):
            action = str(item.get("action", item.get("step", ""))).strip()
        else:
            action = str(item).strip()
        if action:
            steps.append(PlanStep(action=action))

    if not steps:
        return None

    return Plan(goal=goal, steps=steps)


def make_plan(goal: str, steps: list[str]) -> Plan:
    """Safely plan banao — khaali steps filter."""
    clean = [s.strip() for s in steps if s and s.strip()]
    return Plan(goal=goal.strip(), steps=[PlanStep(action=s) for s in clean[:20]])


class PlanTracker:
    """
    Chalu plan ka state (PURE LOGIC).

    Agent context (ctx.scratch) mein rehta hai — har turn ke beech
    plan zinda rehta hai.
    """

    def __init__(self, plan: Plan):
        self.plan = plan
        self.notes: list[str] = []

    def update(self, step_no: int, status: str) -> PlanStep | None:
        """Step ko done/failed/skip karo. Returns: updated step ya None."""
        statuses = {"done": "done", "failed": "failed", "skip": "skipped", "skipped": "skipped"}
        s = statuses.get((status or "").lower())
        if s is None:
            return None
        if not (1 <= step_no <= len(self.plan.steps)):
            return None
        step = self.plan.steps[step_no - 1]
        step.status = s
        return step

    def next_pending(self) -> PlanStep | None:
        """Agla pending step (LLM ko hint dene ke liye)."""
        for step in self.plan.steps:
            if step.status == "pending":
                return step
        return None

    def summary(self) -> str:
        """Progress summary — LLM ko agli baar jaata hai."""
        done, total = self.plan.progress
        failed = sum(1 for s in self.plan.steps if s.status == "failed")
        if self.plan.is_finished:
            if failed:
                return f"Plan POORA HUA ({done}/{total}), {failed} step fail rahe."
            return f"Plan COMPLETE ✅ ({done}/{total})."
        nxt = self.next_pending()
        nxt_text = f' Agla step: "{nxt.action}"' if nxt else ""
        return f"Progress: {done}/{total}.{nxt_text}"

    def format(self) -> str:
        return self.plan.format()


# ======================================================================
#  Tools is file mein NAHI hain — saarthi/tools/planner_tools.py mein
#  hain (circular import se bachne ke liye: direction sirf tools->planner)
