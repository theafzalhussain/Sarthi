"""
Calendar tools — Hinglish mein event banao/dikhaao/hataao.

    "kal subah 9 baje doctor ka appointment rakho"
    "mere is hafte ke events dikhao"
    "3 number event hata do"

Event bane to AUTOMATIC reminder bhi lagta hai (scheduler se) —
ProactiveEngine us reminder pe khud bol dega. Poora circle complete.
"""

from __future__ import annotations

import logging

from .base import Tool, ToolContext
from ..devices.base import ActionResult

log = logging.getLogger("saarthi.tools.calendar")


def _get_store(ctx: ToolContext):
    """ctx.scratch se CalendarStore (agent ne inject kiya hoga)."""
    store = ctx.scratch.get("calendar_store")
    return store


class EventBanaoTool(Tool):
    """Event banao — Hinglish time chalta hai + auto reminder."""

    name = "event_banao"
    description = (
        "Create a calendar event with automatic reminder. "
        "Time accepts Hinglish ('kal subah 9 baje', 'aaj shaam 6', "
        "'2 ghante mein') or ISO ('2026-10-01 09:00'). "
        "Use for: 'doctor ka appointment kal 5 baje rakho'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event kis cheez ka"},
            "when": {
                "type": "string",
                "description": "Kab — Hinglish ya ISO (e.g. 'kal subah 9 baje')",
            },
            "duration_min": {"type": "integer", "description": "Kitna lagega (default 60)"},
            "location": {"type": "string", "description": "Kahan (optional)"},
            "notes": {"type": "string", "description": "Extra jaankari (optional)"},
            "reminder_min_before": {
                "type": "integer",
                "description": "Kitne min pehle reminder (default 15, 0 = nahi)",
            },
        },
        "required": ["title", "when"],
    }

    async def run(
        self,
        ctx: ToolContext,
        title: str,
        when: str,
        duration_min: int = 60,
        location: str = "",
        notes: str = "",
        reminder_min_before: int = 15,
    ) -> ActionResult:
        from ..calendar_store import (
            CalendarStore,
            add_event_with_reminder,
            parse_when,
        )

        store = _get_store(ctx) or CalendarStore()

        epoch = parse_when(when)
        if epoch is None:
            return ActionResult.failure(
                f"Time samajh nahi aaya: '{when}'. Aise bolo: 'kal subah 9 baje', "
                f"'aaj shaam 6 baje', '2 ghante mein', ya '2026-10-01 09:00'"
            )

        event = await add_event_with_reminder(
            store,
            getattr(ctx, "scheduler", None),
            title=title,
            when=epoch,
            duration_min=max(0, int(duration_min or 60)),
            location=location or "",
            notes=notes or "",
            reminder_min_before=max(0, int(reminder_min_before if reminder_min_before is not None else 15)),
        )

        from datetime import datetime

        when_text = datetime.fromtimestamp(event.when).strftime("%a %d %b, %H:%M")
        reminder_note = (
            f" (reminder {event.reminder_min_before} min pehle set)"
            if event.reminder_min_before
            else ""
        )
        return ActionResult.success(
            f"Event ban gaya ✅ #{event.id} — {title} @ {when_text}{reminder_note}"
        )


class EventsDikhaoTool(Tool):
    """Aane wale events dikhao."""

    name = "events_dikhao"
    description = (
        "Show upcoming calendar events. "
        "Use for: 'mere events dikhao', 'is hafte kya kya hai'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Kitne din aage tak (default 7)",
            },
        },
    }

    async def run(self, ctx: ToolContext, days: int = 7) -> ActionResult:
        from ..calendar_store import CalendarStore, format_event_list

        store = _get_store(ctx) or CalendarStore()
        days = max(1, min(int(days or 7), 60))
        events = await asyncio.to_thread(store.upcoming_sync, days, 15)

        return ActionResult.success(
            f"Aane wale {days} din ke events:\n"
            + format_event_list(events, f"Agle {days} din mein koi event nahi hai.")
        )


class EventHataoTool(Tool):
    """Event cancel karo."""

    name = "event_hatao"
    description = (
        "Cancel/delete a calendar event by id (from events_dikhao list). "
        "Use for: 'wo meeting hata do'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "event_id": {"type": "integer", "description": "Event ka id"},
        },
        "required": ["event_id"],
    }

    async def run(self, ctx: ToolContext, event_id: int) -> ActionResult:
        from ..calendar_store import CalendarStore

        store = _get_store(ctx) or CalendarStore()
        ok = await asyncio.to_thread(store.delete_sync, int(event_id))
        if ok:
            return ActionResult.success(f"Event #{event_id} cancel kar diya.")
        return ActionResult.failure(
            f"#{event_id} nahi mila — events_dikhao chala ke sahi id dekho."
        )


def calendar_tools() -> list[Tool]:
    """Saare calendar tools."""
    return [EventBanaoTool(), EventsDikhaoTool(), EventHataoTool()]


import asyncio  # noqa: E402
