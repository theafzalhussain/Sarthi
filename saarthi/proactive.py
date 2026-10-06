"""
Proactive Engine — agent KHUD bolta hai (sirf react nahi karta).

PEHLE:
    User bole tabhi agent zinda hota tha. Bill due, medicine ka time,
    subah ki meeting — kuch nahi batata tha jab tak pucho na.

AB:
    Background loop har 20 sec scheduler check karta hai:
      - reminder due    -> turant announce (voice + UI)
      - missed catch-up -> agent band tha to bhi yaad rakha gaya
      - session start   -> chhoti briefing ("2 kaam aaj ke hain...")

    Ye "presence" wali feel deta hai — JARVIS khud bol raha hai.


DESIGN NOTES:

    1. Announcement callback (on_announce) ASYNC hota hai — voice
       session isme TTS bhejta hai, CLI print karta hai, Telegram
       message bhejta hai. Har UI apna tareeka khud decide karta hai.

    2. FAIL-SAFE: engine crash ho to sirf log hota hai — agent ka
       main loop KABHI nahi rukta. Polling loop apne errors khud
       nigal jaata hai (log karke continue).

    3. Polling (20s default) push nahi hai — par local agent ke liye
       kaafi hai aur zero infra mangta hai.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Awaitable, Callable

from .scheduler import TaskScheduler
from .proactive_context import InterruptionManager

log = logging.getLogger("saarthi.proactive")

# Announcement callback — (title, detail) async bhejo
AnnounceFn = Callable[[str, str], Awaitable[None]]


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "haan", "y", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


# ======================================================================
#  Briefing — session start / "aaj kya hai" ka jawab
# ======================================================================


def build_briefing(tasks: list) -> str:
    """
    Aaj ke tasks ki chhoti, insani briefing (PURE LOGIC — tested).

    >>> build_briefing([])
    ''
    """
    if not tasks:
        return ""

    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 12:
        greet = "Good morning"
    elif 12 <= hour < 17:
        greet = "Good afternoon"
    elif 17 <= hour < 21:
        greet = "Good evening"
    else:
        greet = "Raaste mein ho to bhi"  # raat — thoda sa humor

    count = len(tasks)
    lines = [f"{greet}. Aaj {count} kaam {'hai' if count == 1 else 'hain'}:"]

    # Sirf top 3 — poora list user maange to dikhana
    for task in tasks[:3]:
        rel = _relative_time(task.due_at)
        lines.append(f"  - {task.message} ({rel})")

    extra = count - 3
    if extra > 0:
        lines.append(f"  ...aur {extra} aur")

    return "\n".join(lines)


def _relative_time(due_at: float) -> str:
    """'3 ghante mein', 'kal', 'abhi abhi' — insani waqt."""
    delta = due_at - time.time()

    if delta < 60:
        return "abhi abhi"
    if delta < 3600:
        mins = int(delta / 60)
        return f"{mins} minute mein"
    if delta < 86400:
        hours = int(delta / 3600)
        if hours == 1:
            return "1 ghante mein"
        return f"{hours} ghante mein"

    days = int(delta / 86400)
    if days == 1:
        return "kal"
    return f"{days} din mein"


def format_announcement(task) -> str:
    """Due task ka announcement text (PURE LOGIC — tested)."""
    icon = "🔁" if task.recurrence != "none" else "⏰"
    return f"{icon} Reminder: {task.message}"


# ======================================================================
#  Engine — background polling loop
# ======================================================================


class ProactiveEngine:
    """
    Scheduler ko poll karta hai aur due tasks announce karta hai.

    Use (voice session / jarvis / telegram — sab jagah same):
        engine = ProactiveEngine(scheduler, on_announce=my_speak_fn)
        await engine.start()
        ...
        await engine.stop()
    """

    def __init__(
        self,
        scheduler: TaskScheduler,
        on_announce: AnnounceFn | None = None,
        poll_seconds: float | None = None,
    ):
        self.scheduler = scheduler
        self.on_announce = on_announce
        self.poll_seconds = poll_seconds or _env_float("PROACTIVE_POLL_SECONDS", 20.0)
        self.enabled = _env_bool("PROACTIVE_ENABLED", True)
        self.interruptions = InterruptionManager.from_env(
            self.scheduler.db_path.parent / "proactive_context.db"
        )

        self._task: asyncio.Task | None = None
        self.announced_count = 0

    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Polling loop background mein shuru karo."""
        if not self.enabled:
            log.info("Proactive engine disabled (PROACTIVE_ENABLED=false)")
            return

        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.get_running_loop().create_task(self._run())
        log.info("Proactive engine start (poll=%.0fs)", self.poll_seconds)

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main polling loop — kisi bhi error pe agent nahi rukta."""
        while True:
            try:
                await asyncio.sleep(self.poll_seconds)
                await self.check_once()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Proactive loop error (continue karega): %s", exc)
                await asyncio.sleep(5)

    async def check_once(self) -> list:
        """
        Ek baar due tasks check karo aur announce karo.

        Returns: announce hue tasks (tests ke liye).
        """
        fired = await self.scheduler.pop_due()
        if not fired:
            return []

        for task in fired:
            text = format_announcement(task)
            log.info("Announce: %s", text)
            await self._announce("reminder", text)
            self.interruptions.record(
                f"reminder:{getattr(task, 'id', task.message)}", text, "high"
            )
            self.announced_count += 1

        return fired

    async def suggest(
        self, key: str, text: str, priority: str = "normal", dedupe_hours: float = 12
    ) -> bool:
        """Useful context proactively offer karo, interruption budget ke saath."""
        if not self.enabled or not text.strip():
            return False
        decision = self.interruptions.allow_and_record(
            key.strip() or "suggestion", text.strip(), priority, dedupe_hours
        )
        if not decision.allowed:
            log.debug("Proactive suggestion suppressed: %s", decision.reason)
            return False
        await self._announce("suggestion", text.strip())
        self.announced_count += 1
        return True

    async def _announce(self, kind: str, text: str) -> None:
        if self.on_announce is None:
            log.info("[proactive] %s", text)
            return
        try:
            await self.on_announce(kind, text)
        except Exception as exc:  # noqa: BLE001
            log.warning("Announce fail (engine continues): %s", exc)

    # ------------------------------------------------------------------

    async def briefing(self) -> str:
        """
        Aaj ke tasks ki briefing banao (session start pe boli jaati hai).

        Koi task nahi to khali string — chup rahna bhi ek feature.
        """
        try:
            tasks = await self.scheduler.todays_tasks()
        except Exception as exc:  # noqa: BLE001
            log.warning("Briefing fail: %s", exc)
            return ""
        return build_briefing(tasks)
