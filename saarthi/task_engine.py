"""Durable checkpoint store for long-running autonomous tasks.

Unlike the in-memory PlanTracker, this state survives a process crash/restart.
Execution remains controlled by the agent loop; this module owns task state,
step checkpoints, retry counters, and recovery semantics.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

_TASK_STATES = {"pending", "running", "paused", "completed", "failed", "cancelled"}
_STEP_STATES = {"pending", "running", "done", "failed", "skipped"}


@dataclass(frozen=True)
class DurableStep:
    id: int
    task_id: str
    position: int
    action: str
    status: str
    attempts: int
    max_attempts: int
    note: str
    updated_at: float


@dataclass(frozen=True)
class DurableTask:
    id: str
    goal: str
    status: str
    created_at: float
    updated_at: float
    session_id: str
    last_error: str
    steps: tuple[DurableStep, ...]

    @property
    def progress(self) -> tuple[int, int]:
        resolved = sum(s.status in {"done", "skipped"} for s in self.steps)
        return resolved, len(self.steps)

    @property
    def next_step(self) -> DurableStep | None:
        return next((s for s in self.steps if s.status in {"pending", "failed"}), None)


class DurableTaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS durable_tasks (
                    id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS durable_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES durable_tasks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
                    note TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,
                    UNIQUE(task_id, position)
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON durable_tasks(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_steps_task ON durable_steps(task_id, position);
            """)

    def create(self, goal: str, steps: list[str], session_id: str = "", max_attempts: int = 3) -> DurableTask:
        clean_goal = (goal or "").strip()
        clean_steps = [str(s).strip() for s in steps if str(s).strip()][:20]
        if not clean_goal or not clean_steps:
            raise ValueError("Goal aur kam se kam ek step zaroori hai")
        task_id = uuid.uuid4().hex[:12]
        now = time.time()
        retries = max(1, min(int(max_attempts), 10))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO durable_tasks VALUES (?, ?, 'running', ?, ?, ?, '')",
                (task_id, clean_goal, now, now, session_id),
            )
            conn.executemany(
                """INSERT INTO durable_steps
                   (task_id, position, action, status, attempts, max_attempts, note, updated_at)
                   VALUES (?, ?, ?, 'pending', 0, ?, '', ?)""",
                [(task_id, i, action, retries, now) for i, action in enumerate(clean_steps, 1)],
            )
        task = self.get(task_id)
        assert task is not None
        return task

    def get(self, task_id: str) -> DurableTask | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM durable_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return None
            step_rows = conn.execute(
                "SELECT * FROM durable_steps WHERE task_id=? ORDER BY position", (task_id,)
            ).fetchall()
        steps = tuple(DurableStep(
            id=s["id"], task_id=s["task_id"], position=s["position"], action=s["action"],
            status=s["status"], attempts=s["attempts"], max_attempts=s["max_attempts"],
            note=s["note"], updated_at=s["updated_at"],
        ) for s in step_rows)
        return DurableTask(
            id=row["id"], goal=row["goal"], status=row["status"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            session_id=row["session_id"], last_error=row["last_error"], steps=steps,
        )

    def latest_active(self) -> DurableTask | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id FROM durable_tasks
                   WHERE status IN ('running','paused','pending')
                   ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        return self.get(row["id"]) if row else None

    def list(self, limit: int = 20) -> list[DurableTask]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM durable_tasks ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [task for row in rows if (task := self.get(row["id"])) is not None]

    def update_step(self, task_id: str, position: int, status: str, note: str = "") -> DurableTask:
        normalized = {"skip": "skipped"}.get(status, status)
        if normalized not in _STEP_STATES:
            raise ValueError("Invalid step status")
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        step = next((s for s in task.steps if s.position == int(position)), None)
        if step is None:
            raise IndexError(position)

        attempts = step.attempts + (1 if normalized in {"running", "failed"} else 0)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """UPDATE durable_steps SET status=?, attempts=?, note=?, updated_at=?
                   WHERE task_id=? AND position=?""",
                (normalized, attempts, note[:2000], now, task_id, position),
            )
            refreshed = conn.execute(
                "SELECT status, attempts, max_attempts FROM durable_steps WHERE task_id=?",
                (task_id,),
            ).fetchall()
            if all(r["status"] in {"done", "skipped"} for r in refreshed):
                task_status, error = "completed", ""
            elif any(r["status"] == "failed" and r["attempts"] >= r["max_attempts"] for r in refreshed):
                task_status, error = "paused", note[:2000] or "Step retry limit reached"
            else:
                task_status, error = "running", ""
            conn.execute(
                "UPDATE durable_tasks SET status=?, updated_at=?, last_error=? WHERE id=?",
                (task_status, now, error, task_id),
            )
        updated = self.get(task_id)
        assert updated is not None
        return updated

    def set_status(self, task_id: str, status: str, error: str = "") -> DurableTask:
        if status not in _TASK_STATES:
            raise ValueError("Invalid task status")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE durable_tasks SET status=?, updated_at=?, last_error=? WHERE id=?",
                (status, time.time(), error[:2000], task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(task_id)
        task = self.get(task_id)
        assert task is not None
        return task

    def recover_interrupted(self) -> int:
        """Running steps from a dead process become retryable; tasks become paused."""
        now = time.time()
        with self._connect() as conn:
            steps = conn.execute(
                "UPDATE durable_steps SET status='pending', updated_at=? WHERE status='running'", (now,)
            ).rowcount
            tasks = conn.execute(
                """UPDATE durable_tasks SET status='paused', updated_at=?,
                   last_error='Previous process stopped; safe resume required'
                   WHERE status='running'""", (now,)
            ).rowcount
        return max(steps, tasks)


def format_task(task: DurableTask) -> str:
    icons = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}
    done, total = task.progress
    lines = [f"📋 TASK {task.id} [{task.status.upper()}]: {task.goal}"]
    for step in task.steps:
        retry = f" (try {step.attempts}/{step.max_attempts})" if step.attempts else ""
        lines.append(f"  {icons.get(step.status, '⬜')} {step.position}. {step.action}{retry}")
        if step.note:
            lines.append(f"     ↳ {step.note}")
    lines.append(f"  — {done}/{total} resolved —")
    if task.last_error:
        lines.append(f"  ⚠️ {task.last_error}")
    return "\n".join(lines)
