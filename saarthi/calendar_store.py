"""
Calendar — local events + HINGLISH date parsing (zero dependency, offline).

DESIGN:

    Google Calendar API chahiye OAuth + bhaari deps — ₹0 budget aur
    "purane laptop" ke against. Isliye LOCAL calendar:

        - events SQLite mein (~/.saarthi/calendar.db)
        - Hinglish mein event banao: "kal subah 9 baje doctor"
        - event bane to AUTOMATIC reminder bhi (scheduler se) —
          default 15 min pehle, configurable

    Baad mein Google Calendar sync chahe to isi store ke upar lag
    jaayega (add/get interface saaf hai).


HINGLISH WHEN-PARSER (pure logic — sabse zyada tested hissa):

    Supported patterns:
      "kal subah 9 baje"        -> kal 09:00
      "aaj shaam 6 baje"        -> aaj 18:00
      "parso raat 9"            -> parso 21:00
      "kal 10:30 am"            -> kal 10:30
      "in 2 hours" / "2 ghante mein" -> ab se 2 ghante baad
      "2026-10-01 09:00"        -> ISO seedha
      "monday 5pm"              -> agla monday 17:00

    Subah/shaam/raat/dopahar Hinglish day-parts hain — hour < 12 ho
    aur shaam/raat bola to +12 (6 baje shaam = 18:00).
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

log = logging.getLogger("saarthi.calendar")


# ======================================================================
#  Pure logic — Hinglish "when" parser
# ======================================================================

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3,
    "shukravar": 4, "shanivar": 5, "ravivar": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje)?", re.IGNORECASE)
_REL_MIN_RE = re.compile(r"\b(\d{1,4})\s*(minute|min|mint)\w*\b", re.IGNORECASE)
_REL_HOUR_RE = re.compile(r"\b(\d{1,2})\s*(ghant|hour|hr)\w*\b", re.IGNORECASE)
_REL_DAY_RE = re.compile(r"\b(\d{1,3})\s*(din|day)\w*\b", re.IGNORECASE)


def parse_when(
    text: str,
    now: datetime | None = None,
    default_hour: int = 9,
) -> float | None:
    """
    Hinglish/ISO/relative time text -> epoch seconds (future).

    Returns None jab kuch samajh na aaya — tool tab user se clear
    waqt maangta hai (guess karke galat reminder set karna se accha).

    >>> parse_when("in 10 minutes") is not None
    True
    >>> parse_when("bakwaas kuch bhi") is None
    True
    """
    now = now or datetime.now()
    t = (text or "").strip().lower()
    if not t:
        return None

    # --- 1. ISO format: "2026-10-01 09:00" / "01/10/2026 9am" ---
    iso = _try_iso(t, now)
    if iso is not None:
        return iso

    # --- 2. Relative: "2 ghante mein", "in 30 minutes", "3 din baad" ---
    rel = _try_relative(t, now)
    if rel is not None:
        return rel

    # --- 3. Hinglish absolute: "kal subah 9 baje" ---
    return _try_hinglish_absolute(t, now, default_hour)


def _try_iso(t: str, now: datetime) -> float | None:
    m = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?", t
    )
    if not m:
        return None
    try:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = int(m.group(4) or 9)
        minute = int(m.group(5) or 0)
        dt = now.replace(year=year, month=month, day=day, hour=hour, minute=minute,
                         second=0, microsecond=0)
        return dt.timestamp()
    except ValueError:
        return None


def _try_relative(t: str, now: datetime) -> float | None:
    # "in X minutes" / "X minute baad"
    m = _REL_MIN_RE.search(t)
    if m and ("in " in t or "mein" in t or "baad" in t):
        return (now + timedelta(minutes=int(m.group(1)))).timestamp()

    m = _REL_HOUR_RE.search(t)
    if m:
        return (now + timedelta(hours=int(m.group(1)))).timestamp()

    m = _REL_DAY_RE.search(t)
    if m:
        return (now + timedelta(days=int(m.group(1)))).timestamp()

    # English "in 10 minutes" — number+unit reversed pattern
    m = re.search(r"\bin\s+(\d{1,4})\s*(minute|min|hour|hr|day)s?\b", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith(("min", "minute")):
            return (now + timedelta(minutes=n)).timestamp()
        if unit in ("hour", "hr"):
            return (now + timedelta(hours=n)).timestamp()
        return (now + timedelta(days=n)).timestamp()

    return None


def _try_hinglish_absolute(t: str, now: datetime, default_hour: int) -> float | None:
    hour = minute = None
    ampm = None
    day_shift = 0
    weekday: int | None = None

    # Day part: aaj/kal/parso/tarso
    if re.search(r"\bparso\b", t):
        day_shift = 2
    elif re.search(r"\btarso\b", t):
        day_shift = 3
    elif re.search(r"\bkal\b", t):
        day_shift = 1
    elif re.search(r"\baaj\b", t):
        day_shift = 0

    # Weekday? ("somvar", "monday", "next monday")
    for word, wd in _WEEKDAYS.items():
        if re.search(rf"\b{word}\b", t):
            weekday = wd
            break

    # Time: "9 baje", "9:30", "10 am", "5pm"
    m = _TIME_RE.search(t)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower() or None

        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        # Hinglish day-parts: shaam/raat + 12 (jab chhota hour ho)
        if ampm in (None, "baje"):
            if re.search(r"\b(shaam|sham|saanjh|raat)\b", t) and hour < 12:
                hour += 12
            elif re.search(r"\bdopahar\b", t) and hour < 11:
                hour += 12
    else:
        # Sirf day-part bina hour: "shaam" -> 18:00
        if re.search(r"\b(shaam|sham|saanjh)\b", t):
            hour, minute = 18, 0
        elif re.search(r"\b(raat)\b", t):
            hour, minute = 21, 0
        elif re.search(r"\b(subah|savere)\b", t):
            hour, minute = 9, 0
        elif re.search(r"\b(dopahar)\b", t):
            hour, minute = 13, 0

    if hour is None:
        if day_shift == 0 and weekday is None:
            return None  # kuch samajh nahi aaya
        hour, minute = default_hour, 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if weekday is not None:
        days_ahead = (weekday - target.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # "monday" = agla monday
        target += timedelta(days=days_ahead)
        return target.timestamp()

    target += timedelta(days=day_shift)

    # Time already guzar gaya aur aaj hi bola tha -> kal maan lo
    # ("aaj 5 baje" bola raat 8 baje -> kal 5 baje practical hai)
    if target <= now and day_shift == 0:
        target += timedelta(days=1)

    return target.timestamp()


def format_event_list(events: list, empty_text: str = "Koi event nahi") -> str:
    """Events ki insani list (PURE LOGIC)."""
    if not events:
        return empty_text
    lines = []
    for ev in events:
        dt = datetime.fromtimestamp(ev.when)
        when = dt.strftime("%a %d %b, %H:%M")
        parts = [f"📅 #{ev.id} — {ev.title} ({when})"]
        if ev.duration_min:
            parts[0] += f" · {ev.duration_min} min"
        if ev.location:
            parts[0] += f" · 📍 {ev.location}"
        if ev.notes:
            parts.append(f"       {ev.notes[:100]}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


# ======================================================================
#  Store — SQLite
# ======================================================================


@dataclass
class Event:
    id: int = 0
    title: str = ""
    when: float = 0.0
    duration_min: int = 0
    location: str = ""
    notes: str = ""
    reminder_min_before: int = 0
    created_at: float = field(default_factory=time.time)


class CalendarStore:
    """Local events — SQLite. Restart-proof (scheduler jaisa hi)."""

    def __init__(self, db_path: str | None = None):
        from .config import settings as default_settings

        if db_path is None:
            db_path = str(default_settings.data_dir / "calendar.db")
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    when_ts REAL NOT NULL,
                    duration_min INTEGER DEFAULT 0,
                    location TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    reminder_min_before INTEGER DEFAULT 15,
                    created_at REAL NOT NULL
                )
                """
            )

    # ------------------------------------------------------------------

    def add_sync(
        self,
        title: str,
        when: float,
        duration_min: int = 0,
        location: str = "",
        notes: str = "",
        reminder_min_before: int = 15,
    ) -> Event:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO events (title, when_ts, duration_min, location, notes, "
                "reminder_min_before, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, when, duration_min, location, notes, reminder_min_before, time.time()),
            )
            return Event(
                id=int(cur.lastrowid or 0), title=title, when=when,
                duration_min=duration_min, location=location, notes=notes,
                reminder_min_before=reminder_min_before,
            )

    def upcoming_sync(self, days: int = 7, limit: int = 15) -> list[Event]:
        now = time.time()
        until = now + days * 86400
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE when_ts >= ? AND when_ts <= ? "
                "ORDER BY when_ts LIMIT ?",
                (now - 3600, until, limit),
            ).fetchall()
        return [Event(
            id=r["id"], title=r["title"], when=r["when_ts"],
            duration_min=r["duration_min"], location=r["location"],
            notes=r["notes"], reminder_min_before=r["reminder_min_before"],
        ) for r in rows]

    def get_sync(self, event_id: int) -> Event | None:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            if not r:
                return None
        return Event(
            id=r["id"], title=r["title"], when=r["when_ts"],
            duration_min=r["duration_min"], location=r["location"],
            notes=r["notes"], reminder_min_before=r["reminder_min_before"],
        )

    def delete_sync(self, event_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            return cur.rowcount > 0

    def count_sync(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])


async def add_event_with_reminder(
    store: CalendarStore,
    scheduler,
    title: str,
    when: float,
    duration_min: int = 0,
    location: str = "",
    notes: str = "",
    reminder_min_before: int = 15,
) -> Event:
    """
    Event + auto-reminder dono set karo (ek call, sab kuch).

    Scheduler na ho to bhi event ban jaata hai (reminder optional).
    """
    event = await asyncio.to_thread(
        store.add_sync, title, when, duration_min, location, notes, reminder_min_before
    )

    if scheduler is not None and reminder_min_before > 0:
        remind_at = when - reminder_min_before * 60
        if remind_at > time.time():
            await scheduler.add(
                message=f"📅 {title} — {reminder_min_before} min mein",
                due_at=remind_at,
            )
    return event
