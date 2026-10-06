"""Structured personal intelligence: people, preferences, routines and goals."""
from __future__ import annotations
import sqlite3, time
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PersonalItem:
    id: int; kind: str; subject: str; key: str; value: str
    confidence: float; source: str; created_at: float; updated_at: float

class PersonalStore:
    KINDS = {"person", "preference", "routine", "goal", "project", "correction"}
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._init()
    def _conn(self):
        c=sqlite3.connect(str(self.path), timeout=5); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS personal_items(
              id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, subject TEXT NOT NULL,
              key TEXT NOT NULL, value TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1,
              source TEXT NOT NULL DEFAULT 'user', created_at REAL NOT NULL, updated_at REAL NOT NULL,
              UNIQUE(kind,subject,key));
            CREATE INDEX IF NOT EXISTS idx_personal_lookup ON personal_items(kind,subject,key);
            """)
    def remember(self, kind, subject, key, value, confidence=1.0, source="user"):
        kind=kind.strip().lower(); subject=subject.strip(); key=key.strip().lower(); value=value.strip()
        if kind not in self.KINDS: raise ValueError("Invalid personal-memory kind")
        if not subject or not key or not value: raise ValueError("subject, key aur value zaroori hain")
        confidence=max(0.0,min(float(confidence),1.0)); now=time.time()
        with self._conn() as c:
            c.execute("""INSERT INTO personal_items(kind,subject,key,value,confidence,source,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(kind,subject,key) DO UPDATE SET
              value=excluded.value,confidence=excluded.confidence,source=excluded.source,updated_at=excluded.updated_at""",
              (kind,subject,key,value,confidence,source[:100],now,now))
        return self.get(kind,subject,key)
    def get(self,kind,subject,key):
        with self._conn() as c: r=c.execute("SELECT * FROM personal_items WHERE kind=? AND subject=? AND key=?",
            (kind.lower().strip(),subject.strip(),key.lower().strip())).fetchone()
        return self._item(r) if r else None
    def search(self, query="", kind="", limit=30):
        sql="SELECT * FROM personal_items WHERE 1=1"; p=[]
        if kind: sql+=" AND kind=?"; p.append(kind.lower())
        if query:
            sql+=" AND (subject LIKE ? OR key LIKE ? OR value LIKE ?)"; q=f"%{query}%"; p += [q,q,q]
        sql+=" ORDER BY updated_at DESC LIMIT ?"; p.append(max(1,min(int(limit),100)))
        with self._conn() as c: rows=c.execute(sql,p).fetchall()
        return [self._item(r) for r in rows]
    def forget(self, item_id):
        with self._conn() as c: return c.execute("DELETE FROM personal_items WHERE id=?",(int(item_id),)).rowcount>0
    def context(self, limit=50):
        items=self.search(limit=limit)
        if not items:return ""
        groups={}
        for x in items: groups.setdefault(x.kind,[]).append(f"- {x.subject} · {x.key}: {x.value}")
        return "\n".join(f"[{k.title()}]\n"+"\n".join(v) for k,v in groups.items())
    @staticmethod
    def _item(r): return PersonalItem(r['id'],r['kind'],r['subject'],r['key'],r['value'],r['confidence'],r['source'],r['created_at'],r['updated_at'])
