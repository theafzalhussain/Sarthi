"""Safe undo journal for reversible autonomous actions.

Phase one supports file writes, the highest-value deterministic rollback. Before
a write, original bytes are copied to a private backup. Undo refuses to overwrite
later user edits by comparing the current file hash with the post-action hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_BACKUP_BYTES = 10 * 1024 * 1024


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class UndoEntry:
    token: str
    action: str
    target: str
    status: str
    created_at: float
    undone_at: float | None
    description: str


class RollbackStore:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir) / "undo"
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        self.db_path = self.root / "undo.db"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS undo_entries (
                    token TEXT PRIMARY KEY, action TEXT NOT NULL, target TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL, undone_at REAL,
                    description TEXT NOT NULL, metadata_json TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_undo_status ON undo_entries(status, created_at DESC)"
            )

    def prepare_file_write(self, target: str | Path) -> str | None:
        """Snapshot a file before mutation. Returns token or None if too large."""
        path = Path(target).resolve()
        existed = path.exists()
        if existed and (not path.is_file() or path.stat().st_size > MAX_BACKUP_BYTES):
            return None

        token = uuid.uuid4().hex[:16]
        backup = self.root / f"{token}.bak"
        metadata = {"existed": existed, "backup": str(backup), "before_hash": "", "after_hash": ""}
        if existed:
            data = path.read_bytes()
            backup.write_bytes(data)
            try:
                backup.chmod(0o600)
            except OSError:
                pass
            metadata["before_hash"] = hashlib.sha256(data).hexdigest()

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO undo_entries VALUES (?, 'file_write', ?, 'prepared', ?, NULL, ?, ?)",
                (token, str(path), time.time(), f"Restore file before JARVIS write: {path.name}",
                 json.dumps(metadata)),
            )
        return token

    def finalize_file_write(self, token: str, target: str | Path) -> bool:
        path = Path(target).resolve()
        if not path.is_file():
            self.discard(token)
            return False
        with self._connect() as conn:
            row = conn.execute("SELECT metadata_json FROM undo_entries WHERE token=?", (token,)).fetchone()
            if row is None:
                return False
            metadata = json.loads(row["metadata_json"])
            metadata["after_hash"] = _sha(path)
            conn.execute(
                "UPDATE undo_entries SET status='ready', metadata_json=? WHERE token=?",
                (json.dumps(metadata), token),
            )
        return True

    def discard(self, token: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT metadata_json FROM undo_entries WHERE token=?", (token,)).fetchone()
            conn.execute("DELETE FROM undo_entries WHERE token=?", (token,))
        if row:
            backup = Path(json.loads(row["metadata_json"]).get("backup", ""))
            if backup.is_file():
                backup.unlink(missing_ok=True)

    def _row_to_entry(self, row: sqlite3.Row) -> UndoEntry:
        return UndoEntry(
            token=row["token"], action=row["action"], target=row["target"], status=row["status"],
            created_at=row["created_at"], undone_at=row["undone_at"], description=row["description"],
        )

    def list_ready(self, limit: int = 20) -> list[UndoEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM undo_entries WHERE status='ready' ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def undo(self, token: str = "") -> UndoEntry:
        with self._connect() as conn:
            if token:
                row = conn.execute(
                    "SELECT * FROM undo_entries WHERE token=? AND status='ready'", (token,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM undo_entries WHERE status='ready' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
        if row is None:
            raise KeyError("Ready undo action nahi mila")
        if row["action"] != "file_write":
            raise ValueError("Is action ka rollback handler available nahi hai")

        metadata = json.loads(row["metadata_json"])
        target = Path(row["target"])
        expected_hash = metadata.get("after_hash", "")
        if not target.is_file() or (expected_hash and _sha(target) != expected_hash):
            raise RuntimeError(
                "File JARVIS action ke baad manually badal chuki hai; safe undo ne overwrite rok diya"
            )

        if metadata.get("existed"):
            backup = Path(metadata["backup"])
            if not backup.is_file():
                raise RuntimeError("Undo backup missing hai")
            temp = target.with_name(target.name + f".saarthi-restore-{row['token']}")
            temp.write_bytes(backup.read_bytes())
            os.replace(temp, target)
        else:
            target.unlink()

        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE undo_entries SET status='undone', undone_at=? WHERE token=?",
                (now, row["token"]),
            )
        backup = Path(metadata.get("backup", ""))
        if backup.is_file():
            backup.unlink(missing_ok=True)
        updated = dict(row)
        updated["status"] = "undone"
        updated["undone_at"] = now
        return self._row_to_entry(updated)  # type: ignore[arg-type]
