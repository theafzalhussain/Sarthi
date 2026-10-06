"""Persistent action audit: accountability without leaking secrets."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from saarthi.audit import AuditStore, sanitize


class AuditStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AuditStore(Path(self.tmp.name) / "audit.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_event_restart_ke_baad_bhi_rehta_hai(self):
        self.store.record(tool="file_likho", status="success", arguments={"path": "a.txt"})
        reopened = AuditStore(Path(self.tmp.name) / "audit.db")
        events = reopened.recent()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].tool, "file_likho")
        self.assertEqual(events[0].arguments["path"], "a.txt")

    def test_sensitive_values_database_mein_nahi_jaati(self):
        self.store.record(
            tool="login",
            status="success",
            arguments={"username": "afzal", "password": "super-secret", "api_key": "key-123"},
            message="done",
        )
        event = self.store.recent()[0]
        self.assertEqual(event.arguments["username"], "afzal")
        self.assertEqual(event.arguments["password"], "[REDACTED]")
        self.assertEqual(event.arguments["api_key"], "[REDACTED]")
        self.assertNotIn("super-secret", (Path(self.tmp.name) / "audit.db").read_bytes().decode("latin1"))

    def test_approval_and_failure_reason_saved(self):
        self.store.record(
            tool="mail_bhejo", status="denied", approved=False, risky=True,
            message="User ne mana kar diya", duration_ms=12,
        )
        event = self.store.recent()[0]
        self.assertFalse(event.approved)
        self.assertTrue(event.risky)
        self.assertEqual(event.status, "denied")
        self.assertEqual(event.duration_ms, 12)

    def test_huge_and_binary_values_safe_hain(self):
        result = sanitize({"image": b"abc", "text": "x" * 1500})
        self.assertEqual(result["image"], "[BINARY 3 bytes]")
        self.assertLess(len(result["text"]), 1100)


if __name__ == "__main__":
    unittest.main()
