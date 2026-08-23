#!/usr/bin/env python3
"""
SAARTHI Voice CLI — bolke agent chalao.

Chalane ke liye:
    python voice_cli.py

Pehle setup check kar:
    python voice_cli.py --check

Ek baar sun ke test kar (loop nahi):
    python voice_cli.py --once
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

# ----------------------------------------------------------------------
#  Colors
# ----------------------------------------------------------------------

COLORS = {
    "user": "\033[96m",
    "agent": "\033[92m",
    "tool": "\033[93m",
    "error": "\033[91m",
    "dim": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def paint(text: str, color: str) -> str:
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def show(text: str, color: str = "reset") -> None:
    print(paint(text, color))


BANNER = r"""
   ____    _        _    ____ _____ _   _ ___
  / ___|  / \      / \  |  _ \_   _| | | |_ _|
  \___ \ / _ \    / _ \ | |_) || | | |_| || |
   ___) / ___ \  / ___ \|  _ < | | |  _  || |
  |____/_/   \_\/_/   \_\_| \_\|_| |_| |_|___|

  VOICE MODE — bol ke kaam karwa
"""


# ----------------------------------------------------------------------
#  Event display
# ----------------------------------------------------------------------

# Har event kaise dikhana hai: (prefix, color)
EVENT_STYLE: dict[str, tuple[str, str]] = {
    "calibrating": ("  ...", "dim"),
    "listening": ("  >>>", "user"),
    "thinking": ("  ...", "dim"),
    "corrected": ("  fix", "dim"),
    "heard": ("  tu >", "user"),
    "working": ("  ...", "dim"),
    "reply": ("  saarthi >", "agent"),
    "confirm": ("  !!!", "tool"),
    "approved": ("  ok", "dim"),
    "denied": ("  no", "error"),
    "quiet": ("  ---", "dim"),
    "unclear": ("  ???", "tool"),
    "error": ("  ERR", "error"),
    "info": ("  ---", "dim"),
    "ready": ("  ***", "agent"),
}


def handle_event(kind: str, text: str) -> None:
    """Voice session ke events dikhao."""
    if not text:
        return
    prefix, color = EVENT_STYLE.get(kind, ("  ", "reset"))

    # Multi-line text (setup help) alag se
    if "\n" in text:
        show(f"{prefix}", color)
        for line in text.splitlines():
            show(f"      {line}", color)
        return

    show(f"{prefix} {text}", color)


# ----------------------------------------------------------------------
#  Setup check
# ----------------------------------------------------------------------


async def run_check() -> int:
    """Voice setup check karo aur batao kya missing hai."""
    show(BANNER, "agent")
    show(f"  v{__version__} — setup check\n", "dim")

    problems: list[str] = []

    # --- 1. LLM ---
    show("  1. BRAIN (LLM)", "bold")
    agent = Agent()
    if agent.brain.is_ready:
        show(agent.brain.status(), "dim")
    else:
        show("     Koi API key nahi hai", "error")
        show("     Free key: https://console.groq.com", "dim")
        problems.append("LLM key")

    # --- 2. Mic ---
    show("\n  2. MICROPHONE", "bold")
    if is_audio_available():
        devices = list_input_devices()
        show(f"     {len(devices)} input device mile:", "dim")
        for device in devices[:5]:
            show(f"       {device}", "dim")
    else:
        show("     Mic available nahi hai", "error")
        for line in audio_setup_help().splitlines():
            show(f"     {line}", "dim")
        problems.append("microphone")

    # --- 3. STT ---
    show("\n  3. SPEECH-TO-TEXT (sunna)", "bold")
    if is_stt_available():
        suggested = recommend_model_size()
        show("     faster-whisper ready", "dim")
        show(f"     Tere RAM ke hisaab se model: {suggested}", "dim")
        show(f"     (.env mein WHISPER_MODEL={suggested})", "dim")
    else:
        show("     faster-whisper install nahi hai", "error")
        for line in stt_setup_help().splitlines():
            show(f"     {line}", "dim")
        problems.append("speech-to-text")

    # --- 4. TTS ---
    show("\n  4. TEXT-TO-SPEECH (bolna)", "bold")
    engine = TTSEngine()
    for name, available, quality in TTSEngine.available_backends():
        mark = "OK  " if available else "    "
        color = "dim" if available else "dim"
        show(f"     {mark} {name:<9} {quality}", color)
    show(f"     -> chuna gaya: {engine.backend.name}", "dim")
    if not engine.has_voice:
        show("     Awaaz nahi aayegi (text print hoga)", "tool")
        show("     Awaaz chahiye: sudo apt install espeak-ng", "dim")

    # --- 5. Wake ---
    show("\n  5. WAKE MODE (jagana)", "bold")
    for name, available, description in available_wake_modes():
        mark = "OK  " if available else "    "
        show(f"     {mark} {name:<14} {description}", "dim")

    # --- Verdict ---
    show("\n" + "  " + "=" * 56, "dim")
    if problems:
        show(f"  Ye cheezein missing hain: {', '.join(problems)}", "error")
        show("  Upar ke instructions follow kar.", "dim")
        show("")
        return 1

    show("  Sab ready hai! Chala: python voice_cli.py", "agent")
    show("")
    return 0


# ----------------------------------------------------------------------
#  Main
# ----------------------------------------------------------------------


async def main() -> int:
    args = sys.argv[1:]

    if "--check" in args or "-c" in args:
        return await run_check()

    if "--help" in args or "-h" in args:
        show(__doc__ or "", "dim")
        return 0

    if settings.debug:
        logging.basicConfig(
            level=logging.DEBUG, format="%(levelname)s [%(name)s] %(message)s"
        )

    show(BANNER, "agent")
    show(f"  v{__version__}\n", "dim")

    # --- Agent + session ---
    agent = Agent(on_output=lambda kind, text: None)  # voice session output handle karta hai
    config = VoiceConfig.from_env()
    session = VoiceSession(agent, config, on_event=handle_event)

    # --- Readiness ---
    ready, problems = session.readiness()
    if not ready:
        show("  RUK JA — pehle ye theek kar:\n", "error")
        for problem in problems:
            show(f"    - {problem}", "error")
        show("\n  Detail ke liye chala: python voice_cli.py --check\n", "dim")
        return 1

    # --- Status ---
    show("  " + session.status().replace("\n", "\n  "), "dim")

    if not session.tts.has_voice:
        show(
            "\n  Dhyan: awaaz available nahi hai, jawab print honge.\n"
            "  Awaaz chahiye: sudo apt install espeak-ng",
            "tool",
        )

    show("\n  Band karne ke liye: 'band karo' bol, ya Ctrl+C\n", "dim")

    # --- Single-shot test mode ---
    if "--once" in args:
        show("  [--once mode: ek baar sunke transcribe karunga]\n", "dim")
        await asyncio.to_thread(session.stt.load)
        await session.refresh_vocabulary()
        text = await session.listen_once()
        show(f"\n  Result: {text!r}\n", "agent")
        return 0

    # --- Full loop ---
    try:
        await session.run()
    except KeyboardInterrupt:
        show("\n\n  Bye bhai!\n", "agent")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
