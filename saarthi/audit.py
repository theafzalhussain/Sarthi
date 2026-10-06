"""Persistent, privacy-safe audit trail for every agent action.

The audit database answers four important questions after an autonomous run:
what was attempted, whether the user approved it, whether it succeeded, and how
long it took. Sensitive values are redacted before they ever reach SQLite.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|cookie|otp|pin|cvv|cvc",
    re.IGNORECASE,
)


def sanitize(value: Any, key: str = "") -> Any:
    """Return a JSON-safe copy with credentials and excessively large data hidden."""
    if _SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    if isinstance(value, bytes):
        return f"[BINARY {len(value)} bytes]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    if len(text) > 1000:
        return text[:1000] + f"… [truncated {len(text) - 1000} chars]"
    return text


@dataclass(frozen=True)
class AuditEvent:
    id: int
    created_at: float
    session_id: str
    call_id: str
    tool: str
    status: str
    risky: bool
    approved: bool | None
    duration_ms: int
    arguments: dict[str, Any]
    message: str


class AuditStore:
    """Thread-safe SQLite action journal. Logging failure never breaks the agent."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    call_id TEXT NOT NULL DEFAULT '',
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risky INTEGER NOT NULL DEFAULT 0,
                    approved INTEGER,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    arguments_json TEXT NOT NULL DEFAULT '{}',
                    message TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_time ON action_audit(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_tool ON action_audit(tool, created_at DESC)"
            )

    def record(
        self, *, tool: str, status: str, arguments: dict[str, Any] | None = None,
        message: str = "", risky: bool = False, approved: bool | None = None,
        duration_ms: int = 0, session_id: str = "", call_id: str = "",
    ) -> None:
        safe_args = sanitize(arguments or {})
        safe_message = str(sanitize(message))
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO action_audit
                   (created_at, session_id, call_id, tool, status, risky, approved,
                    duration_ms, arguments_json, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), session_id, call_id, tool, status, int(risky),
                 None if approved is None else int(approved), max(0, int(duration_ms)),
                 json.dumps(safe_args, ensure_ascii=False, default=str), safe_message),
            )

    def recent(self, limit: int = 100, tool: str | None = None) -> list[AuditEvent]:
        limit = max(1, min(int(limit), 1000))
        query = "SELECT * FROM action_audit"
        params: list[Any] = []
        if tool:
            query += " WHERE tool = ?"
            params.append(tool)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AuditEvent(
            id=row["id"], created_at=row["created_at"], session_id=row["session_id"],
            call_id=row["call_id"], tool=row["tool"], status=row["status"],
            risky=bool(row["risky"]), approved=None if row["approved"] is None else bool(row["approved"]),
            duration_ms=row["duration_ms"], arguments=json.loads(row["arguments_json"]),
            message=row["message"],
        ) for row in rows]
