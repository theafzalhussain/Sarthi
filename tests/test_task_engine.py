"""Durable autonomous task checkpoints and recovery."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from saarthi.task_engine import DurableTaskStore


class DurableTaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tasks.db"
        self.store = DurableTaskStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_task_restart_ke_baad_bhi_rehta_hai(self):
        made = self.store.create("Project ready karo", ["files padho", "tests chalao"])
        reopened = DurableTaskStore(self.path)
        loaded = reopened.get(made.id)
        self.assertEqual(loaded.goal, "Project ready karo")
        self.assertEqual(len(loaded.steps), 2)

    def test_steps_checkpoint_and_auto_complete(self):
        task = self.store.create("Do kaam", ["one", "two"])
        updated = self.store.update_step(task.id, 1, "done", "first okay")
        self.assertEqual(updated.status, "running")
        self.assertEqual(updated.progress, (1, 2))
        finished = self.store.update_step(task.id, 2, "done")
        self.assertEqual(finished.status, "completed")

    def test_retry_limit_task_ko_safe_pause_karta_hai(self):
        task = self.store.create("Fragile task", ["try action"], max_attempts=2)
        once = self.store.update_step(task.id, 1, "failed", "network")
        self.assertEqual(once.status, "running")
        twice = self.store.update_step(task.id, 1, "failed", "still down")
        self.assertEqual(twice.status, "paused")
        self.assertIn("still down", twice.last_error)

    def test_crash_recovery_running_action_repeat_nahi_karta(self):
        task = self.store.create("Important", ["send something"])
        self.store.update_step(task.id, 1, "running")
        recovered = DurableTaskStore(self.path)
        self.assertGreaterEqual(recovered.recover_interrupted(), 1)
        loaded = recovered.get(task.id)
        self.assertEqual(loaded.status, "paused")
        self.assertEqual(loaded.steps[0].status, "pending")
        self.assertIn("safe resume", loaded.last_error.lower())

    def test_latest_active_completed_task_skip_karta_hai(self):
        old = self.store.create("old", ["done"])
        self.store.update_step(old.id, 1, "done")
        active = self.store.create("new", ["pending"])
        self.assertEqual(self.store.latest_active().id, active.id)

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create("", [])
        task = self.store.create("valid", ["step"])
        with self.assertRaises(ValueError):
            self.store.update_step(task.id, 1, "nonsense")


if __name__ == "__main__":
    unittest.main()
