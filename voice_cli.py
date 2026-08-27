#!/usr/bin/env python3
"""
SAARTHI Voice CLI — bolke agent chalao.

Chalane ke liye:
    python voice_cli.py

Pehle setup check kar:
    python voice_cli.py --check

Ek baar sun ke test kar (loop nahi):
    python voice_cli.py --once

Look ka pura code `saarthi/ui.py` mein hai — text CLI ke saath
bilkul same theme rehta hai.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from saarthi import __version__  # noqa: E402
from saarthi.agent import Agent  # noqa: E402
from saarthi.config import settings  # noqa: E402
from saarthi.ui import BRAND, ERR, MUTED, OK, TEXT, WARN, Ui  # noqa: E402
from saarthi.voice import (  # noqa: E402
    VoiceConfig,
    VoiceSession,
    audio_setup_help,
    available_wake_modes,
    is_audio_available,
    is_stt_available,
    list_input_devices,
    recommend_model_size,
    stt_setup_help,
)
from saarthi.voice.tts import TTSEngine  # noqa: E402

ui = Ui()

TAGLINE = "Personal AI Agent"


# ----------------------------------------------------------------------
#  Event display
# ----------------------------------------------------------------------

# Voice session ke events -> (nishaan, rang)
EVENT_STYLE: dict[str, tuple[str, str]] = {
    "calibrating": ("think", MUTED),
    "listening": ("mic", BRAND),
    "thinking": ("think", MUTED),
    "corrected": ("arrow", MUTED),
    "heard": ("prompt", BRAND),
    "working": ("run", MUTED),
    "reply": ("ok", OK),
    "confirm": ("warn", WARN),
    "approved": ("ok", OK),
    "denied": ("fail", ERR),
    "quiet": ("bullet", MUTED),
    "unclear": ("warn", WARN),
    "error": ("fail", ERR),
    "info": ("bullet", MUTED),
    "ready": ("on", OK),
}


def handle_event(kind: str, text: str) -> None:
    """Voice session ke events dikhao."""
    if not text:
        return

    symbol_key, color = EVENT_STYLE.get(kind, ("bullet", TEXT))
    mark = ui.sym.get(symbol_key, ui.sym["bullet"])

    # Reply ko panel mein — wo sabse important hai
    if kind == "reply":
        ui.blank()
        ui.reply(text)
        ui.blank()
        return

    # Multi-line (setup help waghairah) — box mein
    if "\n" in text:
        ui.hint(text, title=kind)
        return

    ui.line(f"  {mark}  {text}", color)


# ----------------------------------------------------------------------
#  Setup check
# ----------------------------------------------------------------------


async def run_check() -> int:
    """Voice setup check karo aur batao kya missing hai."""
    ui.banner(__version__, TAGLINE, mode="setup check")

    problems: list[str] = []
    hints: list[tuple[str, str]] = []

    # --- 1. LLM ---
    ui.section("1  Brain (LLM providers)")
    agent = Agent()
    if agent.brain.is_ready:
        ui.brain_table(agent.brain)
    else:
        ui.error("No API key found.")
        problems.append("LLM key")
        hints.append(("brain", settings.setup_help()))
    ui.blank()

    # --- 2. Mic ---
    ui.section("2  Microphone (input)")
    if is_audio_available():
        devices = list_input_devices()
        ui.table(
            ["", "input device"],
            [[ui.badge(True), str(d)] for d in devices[:6]] or [[ui.badge(False), "—"]],
        )
        if len(devices) > 6:
            ui.muted(f"  ... and {len(devices) - 6} more devices")
    else:
        ui.error("No microphone available.")
        problems.append("microphone")
        hints.append(("microphone", audio_setup_help()))
    ui.blank()

    # --- 3. STT ---
    ui.section("3  Speech-to-text (Whisper)")
    if is_stt_available():
        suggested = recommend_model_size()
        ui.table(
            ["", "cheez", "value"],
            [
                [ui.badge(True), "faster-whisper", "ready"],
                [ui.badge(True), "recommended model for your RAM", suggested],
                [ui.badge(True), "add to .env", f"WHISPER_MODEL={suggested}"],
            ],
        )
    else:
        ui.error("faster-whisper is not installed.")
        problems.append("speech-to-text")
        hints.append(("speech-to-text", stt_setup_help()))
    ui.blank()

    # --- 4. TTS ---
    ui.section("4  Text-to-speech (output)")
    engine = TTSEngine()
    ui.table(
        ["", "backend", "quality"],
        [
            [ui.badge(available), name, quality]
            for name, available, quality in TTSEngine.available_backends()
        ],
    )
    ui.muted(f"  selected: {engine.backend.name}")
    if not engine.has_voice:
        hints.append(
            (
                "no voice output",
                "Replies will be printed instead of spoken.\n"
                "To fix: sudo apt install espeak-ng",
            )
        )
    ui.blank()

    # --- 5. Wake ---
    ui.section("5  Wake mode (how to trigger)")
    ui.table(
        ["", "mode", "description"],
        [
            [ui.badge(available), name, description]
            for name, available, description in available_wake_modes()
        ],
    )
    ui.blank()

    # --- Verdict ---
    for title, hint in hints:
        ui.hint(hint, title=title)

    ui.section("Result")
    if problems:
        ui.error(f"Missing: {', '.join(problems)}")
        ui.muted("Follow the instructions above, then run --check again.")
        ui.blank()
        return 1

    ui.success("All set. Run:  python voice_cli.py")
    ui.blank()
    return 0


# ----------------------------------------------------------------------
#  Main
# ----------------------------------------------------------------------


async def main() -> int:
    args = sys.argv[1:]

    if "--check" in args or "-c" in args:
        return await run_check()

    if "--help" in args or "-h" in args:
        ui.banner(__version__, TAGLINE, mode="voice")
        ui.block(__doc__ or "", MUTED)
        return 0

    if settings.debug:
        logging.basicConfig(
            level=logging.DEBUG, format="%(levelname)s [%(name)s] %(message)s"
        )
    else:
        # Raw warnings ko stderr pe chhapne se roko — wo voice ke
        # output ke beech mein aa ke look tod dete hain.
        # (Detail cli.py mein likhi hai.)
        saarthi_log = logging.getLogger("saarthi")
        saarthi_log.addHandler(logging.NullHandler())
        saarthi_log.setLevel(logging.ERROR)

    once = "--once" in args
    ui.banner(__version__, TAGLINE, mode="voice test" if once else "voice mode")

    # --- Agent + session ---
    # Voice session khud output handle karta hai, isliye agent chup rahega
    agent = Agent(on_output=lambda kind, text: None)
    config = VoiceConfig.from_env()
    session = VoiceSession(agent, config, on_event=handle_event)

    # --- Readiness ---
    ready, problems = session.readiness()
    if not ready:
        ui.hint(
            "\n".join(f"- {p}" for p in problems)
            + "\n\nFor details run: python voice_cli.py --check",
            title="setup required",
        )
        return 1

    # --- Status ---
    ui.section("Voice setup")
    ui.block(session.status(), MUTED)
    ui.blank()

    if not session.tts.has_voice:
        ui.muted("No voice output available — replies will be printed (install espeak-ng)")

    ui.blank()

    # --- Single-shot test mode ---
    if once:
        ui.muted("--once mode: listening for a single utterance")
        ui.blank()
        await asyncio.to_thread(session.stt.load)
        await session.refresh_vocabulary()
        text = await session.listen_once()
        ui.blank()
        ui.reply(f"Heard: `{text}`" if text else "Nothing was heard.")
        ui.blank()
        return 0

    ui.line(
        f"  Listening.   {ui.sym['bullet']}   Speak in any language"
        f"   {ui.sym['bullet']}   say 'stop' or press Ctrl+C to exit",
        OK,
    )
    ui.blank()

    # --- Full loop ---
    try:
        await session.run()
    except KeyboardInterrupt:
        ui.blank(2)
        ui.line("  Goodbye.", OK)
        ui.blank()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
