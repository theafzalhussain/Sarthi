"""
Memory Store — SAARTHI ka yaaddasht.

Do tarah ki memory:

1. FACTS (long-term)
   User ke baare mein baatein jo hamesha kaam aayengi.
   "mummy ka number 98xxx hai", "main Jaipur mein rehta hun",
   "mujhe subah 7 baje uthna hota hai"

2. CONVERSATIONS (short-term)
   Purani baatein — taaki "wahi kar do jo pichli baar kiya tha"
   samajh aa sake.

SQLite use kar rahe hain — kyunki:
  - Python mein built-in hai, kuch install nahi karna
  - Ek file, easy backup
  - Budget laptop pe bhi fast (PILLAR #3)
  - Bilkul free

Vector DB (Chroma) baad mein add kar sakte hain semantic search ke liye,
par shuruat mein iski zarurat nahi.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import settings as default_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL,
    category    TEXT    DEFAULT 'general',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    meta        TEXT,
    created_at  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_time    ON conversations(created_at);
"""


@dataclass
class Fact:
    """User ke baare mein ek baat."""

    key: str
    value: str
    category: str = "general"
    updated_at: float = 0.0

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"


@dataclass
class ConversationTurn:
    """Ek conversation message."""

    session_id: str
    role: str
    content: str
    created_at: float = 0.0


class MemoryStore:
    """SQLite-based memory."""

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            db_path = default_settings.data_dir / "memory.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    #  Plumbing
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    async def _run(self, func, *args):
        """
        SQLite sync hai — thread mein chalao taaki async loop block na ho.

        Chhote DB pe ye fast hai, aur aiosqlite dependency bachti hai.
        """
        return await asyncio.to_thread(func, *args)

    # ------------------------------------------------------------------
    #  Facts
    # ------------------------------------------------------------------

    def _remember_sync(self, key: str, value: str, category: str) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (key, value, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    category   = excluded.category,
                    updated_at = excluded.updated_at
                """,
                (key.strip().lower(), value.strip(), category, now, now),
            )

    async def remember(
        self, key: str, value: str, category: str = "general"
    ) -> None:
        """
        Ek baat yaad rakho.

        Same key dobara aaye to update ho jaayega (purani value replace).
        """
        await self._run(self._remember_sync, key, value, category)

    def _recall_sync(self, key: str) -> Fact | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, value, category, updated_at FROM facts WHERE key = ?",
                (key.strip().lower(),),
            ).fetchone()
        if row is None:
            return None
        return Fact(
            key=row["key"],
            value=row["value"],
            category=row["category"],
            updated_at=row["updated_at"],
        )

    async def recall(self, key: str) -> Fact | None:
        """Ek specific baat yaad karo."""
        return await self._run(self._recall_sync, key)

    def _search_sync(self, query: str, limit: int) -> list[Fact]:
        pattern = f"%{query.strip().lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, category, updated_at FROM facts
                WHERE key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
        return [
            Fact(
                key=r["key"],
                value=r["value"],
                category=r["category"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def search_facts(self, query: str, limit: int = 10) -> list[Fact]:
        """Facts mein dhoondo."""
        return await self._run(self._search_sync, query, limit)

    def _all_facts_sync(self, limit: int) -> list[Fact]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, category, updated_at FROM facts
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Fact(
                key=r["key"],
                value=r["value"],
                category=r["category"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def all_facts(self, limit: int = 100) -> list[Fact]:
        """Saari yaad rakhi baatein."""
        return await self._run(self._all_facts_sync, limit)

    def _forget_sync(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM facts WHERE key = ?", (key.strip().lower(),)
            )
            return cursor.rowcount > 0

    async def forget(self, key: str) -> bool:
        """Ek baat bhool jao."""
        return await self._run(self._forget_sync, key)

    # ------------------------------------------------------------------
    #  Conversations
    # ------------------------------------------------------------------

    def _log_sync(
        self, session_id: str, role: str, content: str, meta: str | None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations
                    (session_id, role, content, meta, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, meta, time.time()),
            )

    async def log_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict | None = None,
    ) -> None:
        """Conversation ka ek message save karo."""
        meta_json = json.dumps(meta, ensure_ascii=False) if meta else None
        await self._run(self._log_sync, session_id, role, content, meta_json)

    def _history_sync(
        self, session_id: str | None, limit: int
    ) -> list[ConversationTurn]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT session_id, role, content, created_at
                    FROM conversations WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT session_id, role, content, created_at
                    FROM conversations
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        # Purane se naye order mein wapas karo
        return [
            ConversationTurn(
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in reversed(rows)
        ]

    async def history(
        self, session_id: str | None = None, limit: int = 20
    ) -> list[ConversationTurn]:
        """Purani baatein nikaalo."""
        return await self._run(self._history_sync, session_id, limit)

    def _search_history_sync(self, query: str, limit: int) -> list[ConversationTurn]:
        pattern = f"%{query.strip().lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, role, content, created_at
                FROM conversations WHERE LOWER(content) LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (pattern, limit),
            ).fetchall()
        return [
            ConversationTurn(
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def search_history(
        self, query: str, limit: int = 10
    ) -> list[ConversationTurn]:
        """
        Purani baaton mein dhoondo.

        Yahi "wahi kar do jo pichli baar kiya tha" ko possible banata hai.
        """
        return await self._run(self._search_history_sync, query, limit)

    # ------------------------------------------------------------------
    #  Context for the LLM
    # ------------------------------------------------------------------

    async def build_context(self, max_facts: int = 25) -> str:
        """
        System prompt ke liye memory summary.

        Agent ko user ke baare mein pata hona chahiye — warna wo
        har baar wahi sawaal puchega.
        """
        facts = await self.all_facts(limit=max_facts)
        if not facts:
            return ""

        # Category ke hisaab se group karo — padhne mein aasaan
        grouped: dict[str, list[Fact]] = {}
        for fact in facts:
            grouped.setdefault(fact.category, []).append(fact)

        lines: list[str] = []
        for category in sorted(grouped):
            lines.append(f"[{category}]")
            for fact in grouped[category]:
                lines.append(f"  - {fact.key}: {fact.value}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  Maintenance
    # ------------------------------------------------------------------

    def _stats_sync(self) -> dict[str, int]:
        with self._connect() as conn:
            facts = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
            convs = conn.execute(
                "SELECT COUNT(*) AS n FROM conversations"
            ).fetchone()["n"]
            sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) AS n FROM conversations"
            ).fetchone()["n"]
        return {"facts": facts, "messages": convs, "sessions": sessions}

    async def stats(self) -> dict[str, int]:
        """Memory ka size."""
        return await self._run(self._stats_sync)

    def _prune_sync(self, keep_days: int) -> int:
        cutoff = time.time() - (keep_days * 86400)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE created_at < ?", (cutoff,)
            )
            return cursor.rowcount

    async def prune_old_conversations(self, keep_days: int = 90) -> int:
        """
        Purani conversations delete karo.

        Facts safe rehte hain — sirf chat history saaf hoti hai.
        DB chhota rehta hai, budget device pe fast (PILLAR #3).
        """
        return await self._run(self._prune_sync, keep_days)
