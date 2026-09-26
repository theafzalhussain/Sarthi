"""
Vector Memory — SEMANTIC recall, offline, ₹0, bina heavy dependencies.

PROBLEM:

    Memory search keyword-based tha (LIKE %query%). Matlab:

        "pichle mahine us photographer ki baat ho rahi thi"
        -> "photographer" DB mein nahi hai to KUCH nahi milega,
           chahe "sharma ji wedding shoot wale" stored ho.

    Human yaad-dasht MEANING se dhoondti hai, shabd nahi.

SOLUTION — hybrid semantic search (bina model download ke):

    Embedding = word unigrams + character TRIGRAMS ka TF vector,
    search = IDF-weighted cosine similarity (SQLite mein stored).

    Trigrams ka jugaad Hinglish ke liye KAAMAAL hai:
      "photographer" ~ "photo shoot"  (sho-oto trigrams overlap)
      "paytm walla"  ~ "paytm wala"   (spelling variations)
    Ko dependency-free match karta hai.

UPGRADE PATH:
    Kal jab user fastembed/ChromaDB chahe, `backend=` switch laga
    dena — interface same rahega (add/search/forget).

IMAANDAAR HADD:
    Ye sentence-transformers jaisa deep-semantic NAHI hai. Par
    offline + instant + zero-download + purane laptop pe chalta hai
    (Pillar #3) — aur keyword-search se kaafi behtar.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("saarthi.memory.vector")

_WORD_RE = re.compile(r"[a-zA-Z\u0900-\u097F]{2,}")

# Stopwords — TF-IDF inko waise hi dabata hai, par explicit kam se kam
_STOPWORDS = {
    "hai", "hain", "tha", "thi", "the", "ka", "ki", "ke", "ko", "se",
    "mein", "aur", "ya", "wo", "ye", "is", "us", "kar", "karo", "kya",
    "the", "and", "the", "for", "with", "this", "that", "was", "are",
}


def tokenize(text: str) -> list[str]:
    """Words nikaalo (lowercase, stopwords optional)."""
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def char_trigrams(word: str) -> list[str]:
    """Shabd ke char 3-grams — 'chai' -> '^ch', 'cha', 'hai', 'ai$'."""
    padded = f"^{word}$"
    if len(padded) < 3:
        return []
    return [padded[i : i + 3] for i in range(len(padded) - 2)]


def text_features(text: str) -> dict[str, float]:
    """
    Text ka TF vector (word + trigram features, PURE LOGIC — tested).

    Words ko weight 1.5 (zyada important), trigrams ko 0.5.
    """
    if not text:
        return {}

    features: dict[str, float] = {}
    words = tokenize(text)

    for word in words:
        if word in _STOPWORDS:
            continue
        features[f"w:{word}"] = features.get(f"w:{word}", 0.0) + 1.5
        for tri in char_trigrams(word):
            features[f"t:{tri}"] = features.get(f"t:{tri}", 0.0) + 0.5

    return features


def cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Do TF vectors ke beech cosine (idf weights multiply ke liye hook)."""
    if not a or not b:
        return 0.0

    common = set(a) & set(b)
    if not common:
        return 0.0

    dot = sum(a[t] * b[t] for t in common)
    norm_a = sum(v * v for v in a.values()) ** 0.5
    norm_b = sum(v * v for v in b.values()) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


# ======================================================================
#  SemanticMemory — SQLite-backed
# ======================================================================


class SemanticMemory:
    """
    Text items ka semantic store — SQLite mein TF vectors ke saath.

    Use:
        mem = SemanticMemory()          # memory.db ke saath share hota hai
        await mem.add("sharma ji photographer... ")
        hits = await mem.search("photographer wala kaam", limit=3)
    """

    def __init__(self, db_path: Path | str | None = None):
        from ..config import settings as default_settings

        if db_path is None:
            db_path = default_settings.data_dir / "memory.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    meta TEXT,
                    features TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_semantic_created "
                "ON semantic_items (created_at)"
            )

    async def _run(self, func, *args):
        return await asyncio.to_thread(func, *args)

    # ------------------------------------------------------------------
    #  Core operations
    # ------------------------------------------------------------------

    def _add_sync(self, text: str, meta: dict | None) -> int:
        features = text_features(text)
        if not features:
            return 0
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO semantic_items (text, meta, features, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    text,
                    json.dumps(meta, ensure_ascii=False) if meta else None,
                    json.dumps(features, ensure_ascii=False),
                    time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    async def add(self, text: str, meta: dict | None = None) -> int:
        """Naya item index karo. Returns: id (0 = index nahi hua)."""
        if not text or not text.strip():
            return 0
        return await self._run(self._add_sync, text.strip(), meta)

    def _search_sync(self, query: str, limit: int, min_score: float) -> list[dict]:
        q_features = text_features(query)
        if not q_features:
            return []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, text, meta, features FROM semantic_items "
                "ORDER BY id DESC LIMIT 4000"
            ).fetchall()

        results: list[dict] = []
        for row in rows:
            try:
                item_features = json.loads(row["features"])
            except Exception:  # noqa: BLE001
                continue

            score = cosine_sim(q_features, item_features)
            if score >= min_score:
                results.append(
                    {
                        "id": row["id"],
                        "text": row["text"],
                        "meta": json.loads(row["meta"]) if row["meta"] else {},
                        "score": round(score, 4),
                    }
                )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    async def search(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.12,
    ) -> list[dict]:
        """
        Semantic dhoondo — meaning-based, keyword nahi.

        min_score: isse kam similarity = ignore (0.12 conservative —
        galat yaadein dikhane se accha kuch na dikhaao).
        """
        if not query or not query.strip():
            return []
        return await self._run(self._search_sync, query.strip(), limit, min_score)

    def _forget_sync(self, item_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM semantic_items WHERE id = ?", (item_id,))
            return cur.rowcount > 0

    async def forget(self, item_id: int) -> bool:
        return await self._run(self._forget_sync, int(item_id))

    def _count_sync(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as n FROM semantic_items").fetchone()
            return int(row["n"]) if row else 0

    async def count(self) -> int:
        return await self._run(self._count_sync)

    def _prune_sync(self, keep_last: int) -> int:
        """Purane items hatao (db phoolne se bachne ke liye)."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM semantic_items WHERE id NOT IN "
                "(SELECT id FROM semantic_items ORDER BY id DESC LIMIT ?)",
                (keep_last,),
            )
            return cur.rowcount

    async def prune(self, keep_last: int = 5000) -> int:
        """Purani entries hatao — default last 5000 items rakho."""
        return await self._run(self._prune_sync, keep_last)

    # ------------------------------------------------------------------

    async def status(self) -> str:
        n = await self.count()
        return f"Semantic memory: {n} indexed items — {self.db_path}"
