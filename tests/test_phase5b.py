"""
PHASE 5B — Scheduler, Proactive, Vector memory, Telegram bot.

Sab PURE LOGIC ya temp-db based — network/hardware ki zarurat nahi.
Telegram HTTP layer httpx MockTransport se fake hota hai.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import SaarthiTestCase


# ======================================================================
#  Scheduler — persistent, restart-proof
# ======================================================================


class SchedulerCore(SaarthiTestCase):
    def _scheduler(self) -> "TaskScheduler":
        from saarthi.scheduler import TaskScheduler

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return TaskScheduler(tmp.name)

    def test_add_and_pending(self):
        sched = self._scheduler()
        task = asyncio.get_event_loop_policy().new_event_loop()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        try:
            t = loop.run_until_complete(
                sched.add("chai pi lo", due_in_minutes=10)
            )
            self.assertEqual(t.message, "chai pi lo")
            self.assertEqual(t.recurrence, "none")

            pending = loop.run_until_complete(sched.pending())
            self.assertEqual(len(pending), 1)
            self.assertIn("chai", format(pending[0]))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())

    def test_due_task_fires_and_completes(self):
        sched = self._scheduler()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await sched.add("test alarm", due_in_minutes=0.01)  # ~0.6 sec
            await asyncio.sleep(0.8)
            fired = await sched.pop_due()
            self.assertEqual(len(fired), 1)
            self.assertEqual(fired[0].status, "done")
            # Dobara pop -> khali (one-time hai)
            fired2 = await sched.pop_due()
            self.assertEqual(fired2, [])

        loop.run_until_complete(scenario())

    def test_daily_recurrence_reschedules(self):
        sched = self._scheduler()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await sched.add("medicine", due_in_minutes=0.01, recurrence="daily")
            await asyncio.sleep(0.8)

            fired = await sched.pop_due()
            self.assertEqual(len(fired), 1)

            # Reschedule hua — abhi kuch due nahi
            fired2 = await sched.pop_due()
            self.assertEqual(fired2, [])

            # Pending mein ab bhi hai (agle occurrence pe)
            pending = await sched.pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].message, "medicine")

        loop.run_until_complete(scenario())

    def test_cancel_and_stats(self):
        sched = self._scheduler()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            t = await sched.add("cancel me", due_in_minutes=5)
            self.assertTrue(await sched.cancel(t.id))
            self.assertEqual(await sched.pending(), [])

            stats = await sched.stats()
            self.assertEqual(stats.get("cancelled"), 1)

        loop.run_until_complete(scenario())

    def test_missed_catchup(self):
        """Agent band tha tab due hue tasks — catch-up milte hain."""
        sched = self._scheduler()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            # due_at PEECHHE set karo (simulating missed reminder)
            await sched.add("purana kaam", due_at=time.time() - 3600)
            fired = await sched.pop_due()
            self.assertEqual(len(fired), 1)
            self.assertEqual(fired[0].message, "purana kaam")

        loop.run_until_complete(scenario())

    def test_persistence_across_restart(self):
        """THE test: naya TaskScheduler instance (restart simulation)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))

        from saarthi.scheduler import TaskScheduler

        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            sched1 = TaskScheduler(tmp.name)
            await sched1.add("restart-proof", due_in_minutes=30)

            # RESTART — bilkul naya instance, same db
            sched2 = TaskScheduler(tmp.name)
            pending = await sched2.pending()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].message, "restart-proof")

        loop.run_until_complete(scenario())

    def test_format_task_list(self):
        from saarthi.scheduler import Task, format_task_list

        tasks = [
            Task(id=1, message="chai", due_at=time.time() + 600, recurrence="none"),
            Task(id=2, message="gym", due_at=time.time() + 3600, recurrence="daily"),
        ]
        text = format_task_list(tasks)
        self.assertIn("chai", text)
        self.assertIn("gym", text)
        self.assertIn("#1", text)

        empty = format_task_list([])
        self.assertIn("Koi", empty)


class RecurrenceMath(SaarthiTestCase):
    def test_next_daily_future_hai(self):
        from saarthi.scheduler import next_daily_timestamp

        now = time.time()
        nxt = next_daily_timestamp(now - 3600, now=now)  # 1 ghanta pehle fire tha
        self.assertGreater(nxt, now)
        # 24h +/- 1h ke andar
        self.assertLess(nxt - now, 25 * 3600)

    def test_next_weekly(self):
        from saarthi.scheduler import next_weekly_timestamp

        now = time.time()
        nxt = next_weekly_timestamp(now - 100, now=now)
        self.assertAlmostEqual(nxt - now, 7 * 86400 - 100, delta=5)


# ======================================================================
#  Proactive engine
# ======================================================================


class ProactiveEngineTest(SaarthiTestCase):
    def _setup(self):
        from saarthi.proactive import ProactiveEngine
        from saarthi.scheduler import TaskScheduler

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        sched = TaskScheduler(tmp.name)

        announced: list[tuple[str, str]] = []

        async def announce(kind: str, text: str) -> None:
            announced.append((kind, text))

        engine = ProactiveEngine(sched, on_announce=announce, poll_seconds=0.2)
        return sched, engine, announced

    def test_due_task_announce_hota_hai(self):
        sched, engine, announced = self._setup()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await sched.add("auto alert", due_in_minutes=0.005)
            await engine.start()
            await asyncio.sleep(1.2)
            await engine.stop()

        loop.run_until_complete(scenario())
        self.assertEqual(len(announced), 1)
        self.assertEqual(announced[0][0], "reminder")
        self.assertIn("auto alert", announced[0][1])
        self.assertEqual(engine.announced_count, 1)

    def test_briefing_kaam_karta_hai(self):
        sched, engine, _ = self._setup()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await sched.add("aaj ka kaam", due_in_minutes=120)
            briefing = await engine.briefing()
            return briefing

        briefing = loop.run_until_complete(scenario())
        self.assertIn("aaj ka kaam", briefing)
        self.assertIn("Aaj 1 kaam hai", briefing)

    def test_briefing_khaali_jab_kuch_nahi(self):
        from saarthi.proactive import build_briefing

        self.assertEqual(build_briefing([]), "")


class RelativeTimeTest(SaarthiTestCase):
    def test_relative_time(self):
        from saarthi.proactive import _relative_time

        now = time.time()
        self.assertEqual(_relative_time(now + 30), "abhi abhi")
        self.assertIn("minute", _relative_time(now + 600))
        self.assertIn("ghante", _relative_time(now + 7200))
        # +10s margin — test chalte waqt time.time() aage badh jaata hai
        self.assertEqual(_relative_time(now + 2 * 86400 + 10), "2 din mein")


# ======================================================================
#  Vector memory — semantic recall
# ======================================================================


class VectorMemoryTest(SaarthiTestCase):
    def _memory(self):
        from saarthi.memory.vector import SemanticMemory

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return SemanticMemory(tmp.name)

    def test_features_word_trigram(self):
        from saarthi.memory.vector import text_features

        feats = text_features("photographer chai")
        self.assertIn("w:photographer", feats)
        self.assertTrue(any(k.startswith("t:") for k in feats))
        # stopword dab gaya
        self.assertNotIn("w:hai", feats)

    def test_semantic_search_meaning_match(self):
        """THE test — keyword nahi milte phir bhi meaning se match."""
        mem = self._memory()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await mem.add(
                "sharma ji photographer wale ko advance dena wedding shoot ke liye"
            )
            await mem.add("mummy ko kal call karna hai")
            await mem.add("bijli ka bill 25 tarikh ko due")

            # Query mein 'photographer' GALAT spelling ke saath
            hits = await mem.search("photo wala kaam advance", limit=2)
            return hits

        hits = loop.run_until_complete(scenario())
        self.assertTrue(hits)
        self.assertIn("photographer", hits[0]["text"])

    def test_low_score_filtered(self):
        mem = self._memory()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await mem.add("bijli ka bill due hai")
            # Bilkul unrelated query — high min_score pe kuch nahi
            return await mem.search("space rocket launch", min_score=0.9)

        hits = loop.run_until_complete(scenario())
        self.assertEqual(hits, [])

    def test_forget_and_count(self):
        mem = self._memory()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            item_id = await mem.add("yaad rakhne wali baat")
            self.assertEqual(await mem.count(), 1)
            self.assertTrue(await mem.forget(item_id))
            self.assertEqual(await mem.count(), 0)

        loop.run_until_complete(scenario())

    def test_memory_store_integration(self):
        """MemoryStore.log_turn -> semantic index -> relevant recall."""
        from saarthi.memory.store import MemoryStore

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        os.unlink(tmp.name)
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))

        store = MemoryStore(tmp.name)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await store.log_turn(
                "s1", "user", "sharma ji photographer ko poora payment karna hai shoot ke baad"
            )
            await store.log_turn("s1", "user", "mummy ko call karna")
            # chhota message index NAHI hota (25 char se chhota)
            await store.log_turn("s1", "user", "haan")

            hits = await store.search_relevant_history(
                "photographer ka payment", limit=2
            )
            return hits

        hits = loop.run_until_complete(scenario())
        self.assertTrue(hits)
        self.assertIn("photographer", hits[0]["text"])


# ======================================================================
#  Telegram bot — httpx MockTransport se (koi asli network nahi)
# ======================================================================


class FakeTelegramTransport:
    """
    Telegram API ko fake karta hai — sent messages capture, updates inject.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.updates: list[dict] = []
        self.offset = 0

    def handler(self, request):
        import json

        body = json.loads(request.content.decode())
        path = request.url.path

        if path.endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "test_bot"}})
        if path.endswith("/getUpdates"):
            result = self.updates[self.offset :]
            self.offset = len(self.updates)
            return httpx.Response(200, json={"ok": True, "result": result})
        if path.endswith("/sendMessage"):
            self.sent.append(body)
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "v.ogg"}})
        return httpx.Response(200, json={"ok": True})


class TelegramBotTest(SaarthiTestCase):
    def _bot(self, transport: FakeTelegramTransport, allowed: str = "111, 222"):
        import httpx

        from saarthi.telegram_bot import TelegramBot

        os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
        os.environ["TELEGRAM_ALLOWED_CHAT_IDS"] = allowed
        self.addCleanup(os.environ.pop, "TELEGRAM_BOT_TOKEN", None)
        self.addCleanup(os.environ.pop, "TELEGRAM_ALLOWED_CHAT_IDS", None)

        class TestBot(TelegramBot):
            async def start(self) -> bool:
                # Real network nahi — sirf client + state
                from httpx import AsyncClient

                self._client = AsyncClient(
                    transport=httpx.MockTransport(transport.handler)
                )
                self.running = True
                return True

        from saarthi.agent import Agent

        agent = Agent.__new__(Agent)  # __init__ skip — heavy cheezein nahi chahiye
        agent.confirm = None

        bot = TestBot(agent)
        bot.token = "test:token"
        bot.allowed_chats = {int(x) for x in allowed.split(",")}
        # Mock client — _api() calls isi se jaate hain (koi network nahi)
        bot._client = httpx.AsyncClient(transport=httpx.MockTransport(transport.handler))

        async def _noop_run_agent(text):
            return "Test jawab"

        bot._run_agent = _noop_run_agent  # type: ignore[method-assign]
        return bot

    def test_whitelist_enforced(self):
        transport = FakeTelegramTransport()
        bot = self._bot(transport)

        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await bot._handle_update(
                {"message": {"chat": {"id": 999}, "text": "hello"}}  # 999 allowed NAHI
            )
            await bot._handle_update(
                {"message": {"chat": {"id": 111}, "text": "hello"}}  # allowed
            )

        loop.run_until_complete(scenario())
        # 999 wale ko kuch nahi gaya
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(transport.sent[0]["chat_id"], 111)

    def test_commands_reply(self):
        transport = FakeTelegramTransport()
        bot = self._bot(transport)

        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        async def scenario():
            await bot._handle_update(
                {"message": {"chat": {"id": 111}, "text": "/start"}}
            )
            await bot._handle_update(
                {"message": {"chat": {"id": 111}, "text": "/tasks"}}
            )

        loop.run_until_complete(scenario())
        self.assertEqual(len(transport.sent), 2)
        self.assertIn("JARVIS", transport.sent[0]["text"])

    def test_risky_confirm_hamesha_na(self):
        """SECURITY: Telegram se risky kaam kabhi approve nahi."""
        transport = FakeTelegramTransport()
        bot = self._bot(transport)
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        result = loop.run_until_complete(bot._telegram_confirm("pay_karo", {}))
        self.assertFalse(result)

    def test_configured_check(self):
        transport = FakeTelegramTransport()
        bot = self._bot(transport)
        self.assertTrue(bot.configured)
        bot.token = ""
        self.assertFalse(bot.configured)


if __name__ == "__main__":
    unittest.main()
