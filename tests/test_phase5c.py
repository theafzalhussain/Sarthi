"""
PHASE 5C — Web auth, Email, Calendar, Planner, History compaction.

Sab pure logic ya temp-db — network/hardware ki zarurat nahi.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tests.helpers import SaarthiTestCase


# ======================================================================
#  Web auth — token check
# ======================================================================


class WebAuthTest(SaarthiTestCase):
    def test_token_check(self):
        from saarthi.web.app import check_web_token

        self.assertTrue(check_web_token(None, ""))  # auth off
        self.assertTrue(check_web_token("secret", "secret"))
        self.assertTrue(check_web_token("  secret  ", "secret"))  # trim
        self.assertFalse(check_web_token(None, "secret"))
        self.assertFalse(check_web_token("", "secret"))
        self.assertFalse(check_web_token("wrong", "secret"))

    def test_constant_time_compare(self):
        # secrets.compare_digest use hota hai — timing attack safe
        from saarthi.web.app import check_web_token
        import inspect

        self.assertIn("compare_digest", inspect.getsource(check_web_token))

    def test_protected_paths_covered(self):
        from saarthi.web.app import _PROTECTED_API

        joined = tuple(_PROTECTED_API)
        for path in ("/api/chat", "/api/status", "/api/voice", "/v1/chat/completions"):
            self.assertTrue(any(path.startswith(p) for p in joined), f"missed: {path}")

    def test_middleware_installed_jab_token_ho(self):
        # fastapi (web extra) installed na ho to skip — CI core mein nahi hai
        try:
            import fastapi  # noqa: F401
        except ImportError:
            self.skipTest("fastapi installed nahi hai (optional)")

        os.environ["SAARTHI_WEB_TOKEN"] = "ci-test-token"
        self.addCleanup(os.environ.pop, "SAARTHI_WEB_TOKEN", None)

        from saarthi.web.app import create_app

        app = create_app(agent=None)
        middlewares = [m.cls.__name__ for m in app.user_middleware]
        self.assertIn("TokenAuthMiddleware", middlewares)


# ======================================================================
#  Email — pure logic
# ======================================================================


class EmailPureLogicTest(SaarthiTestCase):
    def test_guess_hosts(self):
        from saarthi.tools.email_tools import guess_mail_hosts

        self.assertEqual(guess_mail_hosts("a@gmail.com"), ("imap.gmail.com", "smtp.gmail.com"))
        self.assertEqual(guess_mail_hosts("a@outlook.com"), ("outlook.office365.com", "smtp.office365.com"))
        self.assertEqual(guess_mail_hosts("a@unknown.xyz"), ("", ""))

    def test_search_criteria(self):
        from saarthi.tools.email_tools import build_search_criteria

        self.assertEqual(build_search_criteria("from:rahul"), 'FROM "rahul"')
        self.assertEqual(build_search_criteria("subject:bill"), 'SUBJECT "bill"')
        self.assertEqual(build_search_criteria("kuch bhi"), 'TEXT "kuch bhi"')
        self.assertEqual(build_search_criteria(""), "ALL")

    def test_extract_body(self):
        import email as email_lib

        from saarthi.tools.email_tools import extract_text_body

        msg = email_lib.message_from_string(
            "Subject: T\nContent-Type: text/plain; charset=utf-8\n\nNamaste bhai"
        )
        self.assertEqual(extract_text_body(msg), "Namaste bhai")

    def test_format_list(self):
        from saarthi.tools.email_tools import MailSummary, format_mail_list

        self.assertEqual(format_mail_list([]), "Koi mail nahi mila.")
        mails = [
            MailSummary(1, "a@x.com", "Bill due", "Mon, 01 Jan", "Pay karna hai", True),
            MailSummary(2, "b@x.com", "Hi", "Tue, 02 Jan", "", False),
        ]
        text = format_mail_list(mails)
        self.assertIn("a@x.com", text)
        self.assertIn("Bill due", text)
        self.assertIn("🔵", text)  # unread flag

    def test_config_missing_ko_handle_karta_hai(self):
        env_backup = {k: os.environ.pop(k, None) for k in
                      ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST")}
        self.addCleanup(os.environ.update, {k: v for k, v in env_backup.items() if v})

        from saarthi.tools.email_tools import is_mail_configured, mail_setup_help

        self.assertFalse(is_mail_configured())
        self.assertIn("EMAIL_ADDRESS", mail_setup_help())


# ======================================================================
#  Calendar — Hinglish when parser + store
# ======================================================================


class HinglishWhenParserTest(SaarthiTestCase):
    def setUp(self):
        super().setUp()
        # Fixed "ab" — deterministic tests
        self.now = datetime(2026, 9, 26, 10, 0, 0)  # Saturday 10 AM

    def _parse(self, text):
        from saarthi.calendar_store import parse_when

        return parse_when(text, now=self.now)

    def test_kal_subah_9_baje(self):
        ts = self._parse("kal subah 9 baje")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual((dt.day - self.now.day), 1)
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 0)

    def test_aaj_shaam_6_baje(self):
        ts = self._parse("aaj shaam 6 baje")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual(dt.day, self.now.day)
        self.assertEqual(dt.hour, 18)

    def test_parso_raat_9(self):
        ts = self._parse("parso raat 9")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual(dt.day - self.now.day, 2)
        self.assertEqual(dt.hour, 21)

    def test_english_pm(self):
        ts = self._parse("kal 5pm")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual(dt.hour, 17)

    def test_relative_ghante(self):
        ts = self._parse("2 ghante mein")
        expected = self.now + timedelta(hours=2)
        self.assertAlmostEqual(ts, expected.timestamp(), delta=5)

    def test_relative_minutes(self):
        ts = self._parse("in 30 minutes")
        expected = self.now + timedelta(minutes=30)
        self.assertAlmostEqual(ts, expected.timestamp(), delta=5)

    def test_iso(self):
        ts = self._parse("2026-10-01 09:00")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 9)

    def test_weekday(self):
        # Aaj Saturday — "somvar/monday" = agla monday (2 din baad)
        ts = self._parse("monday 5pm")
        dt = datetime.fromtimestamp(ts)
        self.assertEqual(dt.weekday(), 0)
        self.assertEqual(dt.hour, 17)

    def test_guzar_gaya_to_kal(self):
        # Abhi 10 AM hai, "aaj 8 baje" bola (subah) -> kal 8 baje
        ts = self._parse("aaj 8 baje")
        dt = datetime.fromtimestamp(ts)
        self.assertGreater(ts, self.now.timestamp())
        self.assertEqual(dt.hour, 8)

    def test_bakwas_pe_none(self):
        self.assertIsNone(self._parse("kuch bhi bakwas"))
        self.assertIsNone(self._parse(""))


class CalendarStoreTest(SaarthiTestCase):
    def _store(self):
        from saarthi.calendar_store import CalendarStore

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return CalendarStore(tmp.name)

    def test_add_get_delete(self):
        store = self._store()
        ev = store.add_sync("Doctor", when=time.time() + 86400, duration_min=30)
        self.assertEqual(ev.title, "Doctor")

        got = store.get_sync(ev.id)
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "Doctor")

        self.assertTrue(store.delete_sync(ev.id))
        self.assertIsNone(store.get_sync(ev.id))

    def test_upcoming_filter(self):
        store = self._store()
        store.add_sync("kal wala", when=time.time() + 86400)
        store.add_sync("agale mahine", when=time.time() + 30 * 86400)

        week = store.upcoming_sync(days=7)
        self.assertEqual(len(week), 1)
        self.assertEqual(week[0].title, "kal wala")

    def test_format(self):
        from saarthi.calendar_store import format_event_list

        store = self._store()
        self.assertIn("Koi event nahi", format_event_list([]))

        ev = store.add_sync("Meeting", when=time.time() + 3600, location="Office")
        text = format_event_list([ev])
        self.assertIn("Meeting", text)
        self.assertIn("Office", text)

    def test_persistence(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))

        from saarthi.calendar_store import CalendarStore

        s1 = CalendarStore(tmp.name)
        s1.add_sync("restart-proof event", when=time.time() + 3600)

        s2 = CalendarStore(tmp.name)  # restart simulation
        self.assertEqual(len(s2.upcoming_sync()), 1)


# ======================================================================
#  Planner — pure logic
# ======================================================================


class PlannerTest(SaarthiTestCase):
    def test_parse_bare_array(self):
        from saarthi.planner import parse_plan_json

        plan = parse_plan_json('["file banao", "test chalao", "commit karo"]')
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].action, "file banao")

    def test_parse_object_with_goal(self):
        from saarthi.planner import parse_plan_json

        plan = parse_plan_json(
            '{"goal": "website banao", "steps": ["design", "code", "deploy"]}'
        )
        self.assertEqual(plan.goal, "website banao")
        self.assertEqual(len(plan.steps), 3)

    def test_parse_json_fence(self):
        from saarthi.planner import parse_plan_json

        text = 'Yeh raha plan:\n```json\n{"steps": ["a", "b"]}\n```'
        plan = parse_plan_json(text)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)

    def test_parse_garbage(self):
        from saarthi.planner import parse_plan_json

        self.assertIsNone(parse_plan_json("kuch json nahi hai"))
        self.assertIsNone(parse_plan_json(""))
        self.assertIsNone(parse_plan_json('{"steps": []}'))

    def test_tracker_progress(self):
        from saarthi.planner import PlanTracker, make_plan

        plan = make_plan("goal", ["step 1", "step 2", "step 3"])
        tracker = PlanTracker(plan)

        self.assertFalse(plan.is_finished)
        tracker.update(1, "done")
        self.assertEqual(plan.progress, (1, 3))
        tracker.update(2, "failed")
        tracker.update(3, "skip")
        self.assertTrue(plan.is_finished)
        # Fail hue steps ke saath honest summary
        self.assertIn("POORA HUA", tracker.summary())
        self.assertIn("1 step fail", tracker.summary())

    def test_tracker_clean_complete(self):
        from saarthi.planner import PlanTracker, make_plan

        tracker = PlanTracker(make_plan("g", ["a", "b"]))
        tracker.update(1, "done")
        tracker.update(2, "done")
        self.assertIn("COMPLETE", tracker.summary())

    def test_tracker_next_pending(self):
        from saarthi.planner import PlanTracker, make_plan

        tracker = PlanTracker(make_plan("g", ["a", "b"]))
        self.assertEqual(tracker.next_pending().action, "a")
        tracker.update(1, "done")
        self.assertEqual(tracker.next_pending().action, "b")

    def test_format_checkboxes(self):
        from saarthi.planner import PlanTracker, make_plan

        tracker = PlanTracker(make_plan("Repo setup", ["clone karo", "test chalao"]))
        tracker.update(1, "done")
        text = tracker.format()
        self.assertIn("📋 PLAN: Repo setup", text)
        self.assertIn("✅ 1. clone karo", text)
        self.assertIn("⬜ 2. test chalao", text)
        self.assertIn("1/2", text)

    def test_invalid_step(self):
        from saarthi.planner import PlanTracker, make_plan

        tracker = PlanTracker(make_plan("g", ["only step"]))
        self.assertIsNone(tracker.update(5, "done"))
        self.assertIsNone(tracker.update(1, "bakwas"))


# ======================================================================
#  History compaction — fake summarizer ke saath
# ======================================================================


class HistoryCompactionTest(SaarthiTestCase):
    def _agent_with_history(self, turns: int):
        from saarthi.agent import Agent
        from saarthi.brain.types import Message, Role

        agent = Agent.__new__(Agent)
        agent.messages = [Message.system("You are JARVIS.")]
        for i in range(turns):
            agent.messages.append(Message.user(f"Purani baat number {i}: project {i} ki details"))
            agent.messages.append(Message.assistant(f"Theek hai, note kar liya {i}"))
        return agent

    def test_compact_karta_hai(self):
        agent = self._agent_with_history(30)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def fake_summary(text: str) -> str:
            return "Saaraansh: user ne 30 projects ki baat ki."

        removed = loop.run_until_complete(agent.compact_history(keep_recent=6, summarize_fn=fake_summary))
        self.assertGreater(removed, 0)
        # Messages kam hue
        self.assertLessEqual(len(agent.messages), 2 + 6 + 1)
        # Summary message aaya
        summary_msgs = [m for m in agent.messages if "SAARAANSH" in (m.content or "")]
        self.assertEqual(len(summary_msgs), 1)
        self.assertIn("30 projects", summary_msgs[0].content)

    def test_recent_messages_bach_jaate_hain(self):
        agent = self._agent_with_history(20)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def fake_summary(text: str) -> str:
            return "ok"

        loop.run_until_complete(agent.compact_history(keep_recent=8, summarize_fn=fake_summary))
        recent_contents = [m.content for m in agent.messages[-4:]]
        self.assertIn("Purani baat number 19: project 19 ki details", recent_contents)

    def test_chhoti_history_pe_kuch_nahi(self):
        agent = self._agent_with_history(5)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def fake_summary(text: str) -> str:
            raise AssertionError("summary call nahi hona chahiye")

        removed = loop.run_until_complete(agent.compact_history(keep_recent=6, summarize_fn=fake_summary))
        self.assertEqual(removed, 0)

    def test_summary_fail_pe_raw_fallback(self):
        agent = self._agent_with_history(30)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def broken_summary(text: str) -> str:
            raise RuntimeError("LLM down")

        removed = loop.run_until_complete(agent.compact_history(keep_recent=6, summarize_fn=broken_summary))
        self.assertGreater(removed, 0)
        summary_msgs = [m for m in agent.messages if "SAARAANSH" in (m.content or "")]
        self.assertEqual(len(summary_msgs), 1)
        # Raw fallback — purana text kuch to hai
        self.assertIn("project", summary_msgs[0].content)

    def test_env_disable(self):
        os.environ["HISTORY_COMPACT"] = "false"
        self.addCleanup(os.environ.pop, "HISTORY_COMPACT", None)

        agent = self._agent_with_history(30)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def fake_summary(text: str) -> str:
            return "x"

        removed = loop.run_until_complete(agent.compact_history(keep_recent=6, summarize_fn=fake_summary))
        self.assertEqual(removed, 0)


if __name__ == "__main__":
    unittest.main()
