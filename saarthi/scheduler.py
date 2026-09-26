"""
Task Scheduler — PERSISTENT reminders aur recurring tasks.

PROBLEM (ye module kyun hai):

    Pehle `reminder_set` sirf `asyncio.create_task` tha. Matlab:

        PC restart / agent band -> reminder GAYAB. Hamesha ke liye.

    Ek asli Jarvis ke liye ye deal-breaker hai. "Kal subah 8 baje
    medicine yaad dilana" — 3 ghante pehle PC band hua to kaam se gaya.

SOLUTION — SQLite-backed scheduler:

    - Har task DB mein (same folder as memory.db) — restart-proof
    - RECURRING tasks: "roz subah 8 baje" -> daily reschedule khud
    - MISSED catch-up: agent band tha tab due hue tasks yaad rakhe
      jaate hain -> agent agli baar start ho to turant bata deta hai
    - Pure logic core (due calc, recurrence) alag — bina I/O test hota hai


DESIGN NOTE:

    Waqt epoch seconds (UTC) mein store hota hai — DST/timezone ke
    kadve se bachne ke liye. Display ke waqt hi local time banate hain.

    Daily recurrence ka matlab: same LOCAL wall-clock time, agla
    occurrence. `next_daily_timestamp()` ise handle karta hai.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("saarthi.scheduler")


# ======================================================================
#  Task model
# ======================================================================


@dataclass
class Task:
    """Ek scheduled kaam."""

    id: int = 0
    message: str = ""
    due_at: float = 0.0            # epoch seconds (UTC)
    recurrence: str = "none"       # none | daily | weekly
    status: str = "pending"        # pending | done | cancelled | missed
    kind: str = "reminder"         # reminder | todo
    created_at: float = field(default_factory=time.time)

    def due_text(self) -> str:
        """Insani waqt mein due — display ke liye."""
        dt = datetime.fromtimestamp(self.due_at)
        return dt.strftime("%d %b, %H:%M")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "due_at": self.due_at,
            "due_text": self.due_text(),
            "recurrence": self.recurrence,
            "status": self.status,
        }


# ======================================================================
#  Pure logic — recurrence math (I/O ke bina test hota hai)
# ======================================================================


def next_daily_timestamp(due_at: float, now: float | None = None) -> float:
    """
    Daily task ka agla due — same LOCAL wall-clock time.

    Agla occurrence aaj ya kal, par hamesha FUTURE mein.

    >>> t = next_daily_timestamp(1758860400.0, now=1758860401.0) > 1758860401.0
    >>> t
    True
    """
    now = now if now is not None else time.time()

    due_dt = datetime.fromtimestamp(due_at)
    candidate = due_dt + timedelta(days=1)

    # Agla occurrence kal ke nahi, AAJ ke usi time pe bhi ho sakta hai
    # (agar wo abhi tak nahi aaya) — e.g. abhi subah 6 baje hai, task
    # roz subah 8 baje: aaj ke 8 baje wala sahi hai.
    today_candidate = due_dt.replace(
        year=datetime.fromtimestamp(now).year,
        month=datetime.fromtimestamp(now).month,
        day=datetime.fromtimestamp(now).day,
    )
    if today_candidate.timestamp() > now:
        return today_candidate.timestamp()

    return candidate.timestamp()


def next_weekly_timestamp(due_at: float, now: float | None = None) -> float:
    """Weekly task ka agla due — same weekday + time, 7 din baad."""
    now = now if now is not None else time.time()
    return datetime.fromtimestamp(due_at).timestamp() + 7 * 86400


def next_occurrence(task: Task, now: float | None = None) -> float | None:
    """
    Task ka agla due nikalo (recurring ke liye).

    Returns: None agar recur nahi karna (none/unknown recurrence).
    """
    if task.recurrence == "daily":
        return next_daily_timestamp(task.due_at, now)
    if task.recurrence == "weekly":
        return next_weekly_timestamp(task.due_at, now)
    return None


def format_task_list(tasks: list[Task], empty_text: str = "Koi task nahi") -> str:
    """
    Tasks ki insani list — LLM ko aur user ko dono ke kaam ki.
    """
    if not tasks:
        return empty_text

    lines: list[str] = []
    for task in tasks:
        icon = {"daily": "🔁", "weekly": "📅"}.get(task.recurrence, "⏰")
        lines.append(f"  {icon} #{task.id} — {task.message} ({task.due_text()})")
    return "\n".join(lines)


# ======================================================================
#  Scheduler — SQLite persistence
# ======================================================================


class TaskScheduler:
    """
    Persistent task scheduler — restart-proof reminders.

    Use:
        sched = TaskScheduler()                  # ~/.saarthi/scheduler.db
        await sched.add("chai peene ka time", due_in_minutes=10)
        tasks = await sched.pop_due()            # due hue tasks (fired)
    """

    def __init__(self, db_path: Path | str | None = None):
        from .config import settings as default_settings

        if db_path is None:
            db_path = default_settings.data_dir / "scheduler.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    due_at REAL NOT NULL,
                    recurrence TEXT NOT NULL DEFAULT 'none',
                    status TEXT NOT NULL DEFAULT 'pending',
                    kind TEXT NOT NULL DEFAULT 'reminder',
                    created_at REAL NOT NULL
                )
                """
            )

    async def _run(self, func, *args):
        """Blocking SQLite ko thread mein chalao (event loop na ruke)."""
        return await asyncio.to_thread(func, *args)

    # ------------------------------------------------------------------
    #  CRUD
    # ------------------------------------------------------------------

    def _add_sync(self, message: str, due_at: float, recurrence: str, kind: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (message, due_at, recurrence, status, kind, created_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (message, due_at, recurrence, kind, time.time()),
            )
            return int(cur.lastrowid or 0)

    async def add(
        self,
        message: str,
        due_at: float | None = None,
        due_in_minutes: float | None = None,
        recurrence: str = "none",
        kind: str = "reminder",
    ) -> Task:
        """Naya task. due_at (epoch) YA due_in_minutes — koi ek."""
        if due_at is None:
            minutes = max(0.01, float(due_in_minutes or 1.0))
            due_at = time.time() + minutes * 60

        recurrence = recurrence if recurrence in ("none", "daily", "weekly") else "none"
        task_id = await self._run(self._add_sync, message, float(due_at), recurrence, kind)
        log.info("Task #%d: %s (due %.0fs, %s)", task_id, message, due_at - time.time(), recurrence)

        return Task(
            id=task_id,
            message=message,
            due_at=float(due_at),
            recurrence=recurrence,
            kind=kind,
        )

    def _get_sync(self, task_id: int) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return Task(**dict(row)) if row else None

    async def get(self, task_id: int) -> Task | None:
        return await self._run(self._get_sync, task_id)

    def _set_status_sync(self, task_id: int, status: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
            return cur.rowcount > 0

    async def cancel(self, task_id: int) -> bool:
        """Task cancel karo (recurring ko bhi)."""
        ok = await self._run(self._set_status_sync, task_id, "cancelled")
        if ok:
            log.info("Task #%d cancelled", task_id)
        return ok

    async def complete(self, task_id: int) -> bool:
        return await self._run(self._set_status_sync, task_id, "done")

    # ------------------------------------------------------------------
    #  Queries
    # ------------------------------------------------------------------

    def _list_sync(self, status: str, limit: int) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY due_at LIMIT ?",
                (status, limit),
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    async def pending(self, limit: int = 20) -> list[Task]:
        return await self._run(self._list_sync, "pending", limit)

    def _due_sync(self, now: float) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND due_at <= ? ORDER BY due_at",
                (now,),
            ).fetchall()
            return [Task(**dict(r)) for r in rows]

    def _reschedule_sync(self, task_id: int, next_due: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET due_at = ?, status = 'pending' WHERE id = ?",
                (next_due, task_id),
            )

    def _mark_sync(self, task_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))

    async def pop_due(self) -> list[Task]:
        """
        Due hue tasks nikalo (aur handle karo):

        - one-time  -> status = 'done'
        - recurring -> agle occurrence pe reschedule

        Agent band tha to bhi due tasks yahan milenge (catch-up).
        """
        now = time.time()
        due = await self._run(self._due_sync, now)

        fired: list[Task] = []
        for task in due:
            next_due = next_occurrence(task, now)
            if next_due is not None:
                await self._run(self._reschedule_sync, task.id, next_due)
                # fired copy mein original due rakho — display ke liye
                fired.append(task)
            else:
                await self._run(self._mark_sync, task.id, "done")
                task.status = "done"
                fired.append(task)

        if fired:
            log.info("Scheduler: %d task fire hue", len(fired))
        return fired

    async def todays_tasks(self) -> list[Task]:
        """Aaj ke (24 ghante ke andar due) pending tasks — briefing ke liye."""
        pending = await self.pending(limit=50)
        now = time.time()
        return [t for t in pending if t.due_at <= now + 86400]

    # ------------------------------------------------------------------

    def _stats_sync(self) -> dict:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM tasks GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["n"] for r in rows}
            total = sum(counts.values())
            return {"total": total, **counts}

    async def stats(self) -> dict:
        return await self._run(self._stats_sync)

    # ------------------------------------------------------------------

    def status(self) -> str:
        """CLI display ke liye chhoti line."""
        try:
            stats = self._stats_sync()
            pending = stats.get("pending", 0)
            return f"Scheduler: {pending} pending task(s) — {self.db_path}"
        except Exception:  # noqa: BLE001
            return f"Scheduler: db issue — {self.db_path}"
