"""Safe reversible file actions."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from saarthi.rollback import RollbackStore


class RollbackStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = RollbackStore(self.root / "data")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_with_checkpoint(self, path: Path, content: str) -> str:
        token = self.store.prepare_file_write(path)
        self.assertIsNotNone(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.assertTrue(self.store.finalize_file_write(token, path))
        return token

    def test_new_file_undo_delete_karta_hai(self):
        path = self.root / "new.txt"
        token = self._write_with_checkpoint(path, "created")
        self.store.undo(token)
        self.assertFalse(path.exists())

    def test_overwrite_undo_original_restore_karta_hai(self):
        path = self.root / "existing.txt"
        path.write_text("original", encoding="utf-8")
        token = self._write_with_checkpoint(path, "changed")
        self.store.undo(token)
        self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_append_undo_original_restore_karta_hai(self):
        path = self.root / "log.txt"
        path.write_text("one\n", encoding="utf-8")
        token = self.store.prepare_file_write(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("two\n")
        self.store.finalize_file_write(token, path)
        self.store.undo(token)
        self.assertEqual(path.read_text(encoding="utf-8"), "one\n")

    def test_later_user_edit_safe_undo_rokta_hai(self):
        path = self.root / "work.txt"
        path.write_text("before", encoding="utf-8")
        token = self._write_with_checkpoint(path, "jarvis change")
        path.write_text("user changed later", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.store.undo(token)
        self.assertEqual(path.read_text(encoding="utf-8"), "user changed later")

    def test_latest_ready_undo_and_persistence(self):
        first = self._write_with_checkpoint(self.root / "a.txt", "a")
        second_path = self.root / "b.txt"
        second = self._write_with_checkpoint(second_path, "b")
        reopened = RollbackStore(self.root / "data")
        self.assertEqual(reopened.list_ready()[0].token, second)
        entry = reopened.undo()
        self.assertEqual(entry.token, second)
        self.assertFalse(second_path.exists())
        self.assertEqual(reopened.list_ready()[0].token, first)

    def test_failed_write_snapshot_discard_hota_hai(self):
        path = self.root / "unused.txt"
        token = self.store.prepare_file_write(path)
        self.store.discard(token)
        self.assertEqual(self.store.list_ready(), [])


if __name__ == "__main__":
    unittest.main()
