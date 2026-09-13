#!/usr/bin/env python3
"""
======================================================================
  J.A.R.V.I.S. — Just A Rather Very Intelligent System
  Advanced Agentic AI Assistant with Multimodal Voice + Web & OS Control
======================================================================

Usage:
    python jarvis.py              (start terminal + background web server)
    python jarvis.py --mute       (start with voice output muted)
    python jarvis.py --voice      (start directly in voice listening mode)
    python jarvis.py --no-web     (disable web server, CLI only)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from saarthi import __version__
from saarthi.agent import Agent
from saarthi.config import Settings
from saarthi.tools.safety import format_confirmation, is_affirmative
from saarthi.ui import BRAND, ERR, MUTED, OK, TEXT, WARN, Ui
from saarthi.voice.tts import TTSEngine
from saarthi.web.app import create_app, get_local_ip

ui = Ui()
TAGLINE = "J.A.R.V.I.S. Core"

VOICE_OUTPUT_ENABLED = True
LOCAL_IP = get_local_ip()
WEB_PORT = 8000


# ----------------------------------------------------------------------
#  Background Web Server for Phone & VS Code Access
# ----------------------------------------------------------------------

def start_background_web(agent: Agent, host: str = "0.0.0.0", port: int = 8000) -> bool:
    """Start the FastAPI Web UI and VS Code OpenAI endpoint in a background thread."""
    try:
        import uvicorn

        app = create_app(agent)
        config = uvicorn.Config(app=app, host=host, port=port, log_level="error")
        server = uvicorn.Server(config)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        return True
    except Exception as exc:
        logging.getLogger("jarvis").debug("Web server start failed: %s", exc)
        return False


# ----------------------------------------------------------------------
#  Confirmation prompt for risky actions
# ----------------------------------------------------------------------

async def ask_confirmation(action: str, details: dict) -> bool:
    """Confirmation handler with safety prompt."""
    ui.blank()
    ui.hint(format_confirmation(action, details), title="JARVIS SAFETY PROTOCOL")

    prompt = (
        "  "
        + ui.paint("Approve this action, Sir? [y / n]", WARN, bold=True)
        + " "
        + ui.paint("❯", WARN)
        + " "
    )

    try:
        answer = await asyncio.to_thread(input, prompt)
    except (EOFError, KeyboardInterrupt):
        ui.error("Protocol aborted.")
        return False

    approved = is_affirmative(answer)
    if approved:
        ui.success("Action confirmed. Executing...")
    else:
        ui.error("Action denied. Aborted.")
    ui.blank()
    return approved


# ----------------------------------------------------------------------
#  HUD Display & Hardware Diagnostics
# ----------------------------------------------------------------------

def render_hud(agent: Agent, tts: TTSEngine) -> None:
    """Render the Iron-Man inspired status HUD."""
    import psutil

    # 1. Brain & Provider
    active_provider = "None"
    if agent.brain.providers:
        active_provider = agent.brain.providers[0].name.upper()

    # 2. Hardware stats
    try:
        cpu_pct = psutil.cpu_percent(interval=0.05)
        mem = psutil.virtual_memory()
        mem_str = f"{mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB ({mem.percent}%)"
        battery = psutil.sensors_battery()
        if battery:
            plug = "⚡" if battery.power_plugged else "🔋"
            batt_str = f"{plug} {battery.percent}%"
        else:
            batt_str = "🔌 AC Power"
    except Exception:
        cpu_pct = 0
        mem_str = "N/A"
        batt_str = "N/A"

    # 3. Voice backend
    voice_backend = tts.backend.name.upper()
    voice_status = f"{voice_backend} ({'ACTIVE' if VOICE_OUTPUT_ENABLED else 'MUTED'})"

    ui.blank()
    ui.rule()
    print(ui.paint("   ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗   ", BRAND, bold=True))
    print(ui.paint("   ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝   ", BRAND, bold=True))
    print(ui.paint("   ██║███████║██████╔╝██║   ██║██║███████╗   ", BRAND, bold=True))
    print(ui.paint("██ ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║   ", BRAND, bold=True))
    print(ui.paint("╚████║██║  ██║██║  ██║ ╚████╔╝ ██║███████║   ", BRAND, bold=True))
    print(ui.paint(" ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝   ", BRAND, bold=True))
    ui.rule()

    # Diagnostic Badges
    badges = [
        f"🧠 BRAIN: {ui.paint(active_provider, OK)}",
        f"🎙️ VOICE: {ui.paint(voice_status, OK if VOICE_OUTPUT_ENABLED else WARN)}",
        f"💻 CPU: {ui.paint(f'{cpu_pct}%', OK)}",
        f"📊 RAM: {ui.paint(mem_str, OK)}",
        f"🔋 PWR: {ui.paint(batt_str, OK)}",
    ]
    print("  " + "  │  ".join(badges))
    ui.rule()

    # Universal Connectivity Info
    print(f"  🌐 {ui.paint('WEB DASHBOARD:', OK, bold=True)}  http://localhost:{WEB_PORT}")
    print(f"  📱 {ui.paint('PHONE / TABLET:', BRAND, bold=True)}  http://{LOCAL_IP}:{WEB_PORT}  (Open in Phone Browser to install app)")
    print(f"  💻 {ui.paint('VS CODE API:', WARN, bold=True)}     http://localhost:{WEB_PORT}/v1  (Connects with Continue.dev / Cursor)")
    ui.rule()
    ui.blank()
    ui.muted("  Type a command, or press [Enter] / type '/v' to speak with Jarvis.")
    ui.muted("  Shortcuts: /v (voice), /web (open browser UI), /m (mute/unmute), /sys (HUD), /clear, /quit")
    ui.blank()


# ----------------------------------------------------------------------
#  Voice capture helper (Faster-Whisper)
# ----------------------------------------------------------------------

async def capture_voice_input() -> str | None:
    """Capture microphone audio and transcribe via faster-whisper."""
    try:
        from saarthi.voice import VoiceConfig, is_audio_available, is_stt_available
        from saarthi.voice.audio import AudioRecorder
        from saarthi.voice.stt import SpeechRecognizer

        if not is_audio_available():
            ui.error("Microphone device not detected.")
            return None

        if not is_stt_available():
            ui.error("faster-whisper is not installed. Run: pip install faster-whisper")
            return None

        ui.line("  🎙️  Listening, Sir... (speak now)", BRAND)
        config = VoiceConfig.from_env()
        recorder = AudioRecorder(config.audio)
        stt = SpeechRecognizer(config.stt)

        await asyncio.to_thread(stt.load)
        audio, status = await asyncio.to_thread(recorder.record_until_silence)

        if audio is None or len(audio) == 0:
            ui.muted("  (Nothing heard)")
            return None

        result = await asyncio.to_thread(stt.transcribe, audio)
        if result and result.text:
            cleaned = result.text.strip()
            ui.line(f"  🗣️  You said: {ui.paint(cleaned, TEXT, bold=True)}", BRAND)
            return cleaned

        ui.muted("  (Could not understand audio)")
        return None

    except Exception as exc:  # noqa: BLE001
        ui.error(f"Voice capture error: {exc}")
        return None


# ----------------------------------------------------------------------
#  Main Jarvis Loop
# ----------------------------------------------------------------------

async def main() -> int:
    global VOICE_OUTPUT_ENABLED

    # 1. Config & Persona
    settings = Settings.load()
    settings.jarvis_mode = True

    # 2. Setup Agent & TTS Engine
    tts = TTSEngine()
    agent = Agent(config=settings, confirm=ask_confirmation)

    # 3. Start Background Web Server
    if "--no-web" not in sys.argv:
        start_background_web(agent, host="0.0.0.0", port=WEB_PORT)

    # CLI args
    if "--mute" in sys.argv:
        VOICE_OUTPUT_ENABLED = False
    start_in_voice = "--voice" in sys.argv

    # Initial Welcome Chime & Speech
    render_hud(agent, tts)
    welcome_text = "Jarvis online and at your service, Sir. How may I assist you today?"
    ui.reply(welcome_text)
    if VOICE_OUTPUT_ENABLED:
        asyncio.create_task(asyncio.to_thread(tts.say, welcome_text))

    # Single voice run if --voice
    if start_in_voice:
        spoken = await capture_voice_input()
        if spoken:
            await process_input(spoken, agent, tts)

    # REPL Loop
    while True:
        try:
            prompt_str = "  " + ui.paint("JARVIS", BRAND, bold=True) + " " + ui.paint("❯", BRAND) + " "
            user_input = await asyncio.to_thread(input, prompt_str)
            user_input = user_input.strip()

            # Empty Enter -> quick voice trigger!
            if not user_input:
                spoken = await capture_voice_input()
                if spoken:
                    await process_input(spoken, agent, tts)
                continue

            # Command shortcuts
            cmd_lower = user_input.lower()
            if cmd_lower in ("/quit", "/exit", "quit", "exit", "shutdown"):
                farewell = "Shutting down systems. Goodbye, Sir."
                ui.reply(farewell)
                if VOICE_OUTPUT_ENABLED:
                    tts.say(farewell)
                break

            elif cmd_lower in ("/v", "/voice", "voice", "bolo"):
                spoken = await capture_voice_input()
                if spoken:
                    await process_input(spoken, agent, tts)
                continue

            elif cmd_lower in ("/web", "/ui", "web"):
                url = f"http://localhost:{WEB_PORT}"
                ui.line(f"  🌐 Opening JARVIS Web Dashboard: {url}", BRAND)
                webbrowser.open(url)
                continue

            elif cmd_lower in ("/ip", "/phone", "phone"):
                ui.section("Universal Device Access")
                ui.line(f"  📱 On your Phone / Tablet, open: http://{LOCAL_IP}:{WEB_PORT}", OK)
                ui.line("  💡 Tip: In Chrome/Safari, tap 'Add to Home Screen' to install as a native App!", TEXT)
                ui.blank()
                continue

            elif cmd_lower in ("/m", "/mute", "mute"):
                VOICE_OUTPUT_ENABLED = not VOICE_OUTPUT_ENABLED
                state = "MUTED" if not VOICE_OUTPUT_ENABLED else "ACTIVE"
                ui.line(f"  🎙️ Voice output is now {state}.", WARN if not VOICE_OUTPUT_ENABLED else OK)
                continue

            elif cmd_lower in ("/sys", "/status", "status"):
                render_hud(agent, tts)
                continue

            elif cmd_lower in ("/clear", "cls", "clear"):
                os.system("cls" if os.name == "nt" else "clear")
                render_hud(agent, tts)
                continue

            elif cmd_lower in ("/tools", "tools"):
                ui.section("Available System & Agent Tools (57+)")
                ui.block(agent.tools.describe(), MUTED)
                continue

            elif cmd_lower in ("/help", "help", "/h"):
                ui.section("JARVIS Control Guide")
                ui.line("  - Type any command in natural Hinglish or English.", TEXT)
                ui.line("  - Press [Enter] on empty prompt to activate Microphone Voice input.", TEXT)
                ui.line("  - /web          : Open Web & Mobile Dashboard in Browser", TEXT)
                ui.line("  - /phone        : Show URL to connect from Phone / Tablet", TEXT)
                ui.line("  - /v or /voice  : Activate Voice listening immediately", TEXT)
                ui.line("  - /m or /mute   : Toggle spoken voice responses", TEXT)
                ui.line("  - /sys          : Show live CPU, RAM, Battery & Network HUD", TEXT)
                ui.line("  - /clear        : Clear terminal and refresh dashboard", TEXT)
                ui.line("  - /quit         : Exit Jarvis", TEXT)
                ui.blank()
                continue

            # Regular command execution
            await process_input(user_input, agent, tts)

        except (KeyboardInterrupt, EOFError):
            ui.blank()
            ui.line("  Goodbye, Sir.", OK)
            break
        except Exception as exc:  # noqa: BLE001
            ui.error(f"Error: {exc}")

    return 0


async def process_input(text: str, agent: Agent, tts: TTSEngine) -> None:
    """Process user prompt, stream response, and speak aloud."""
    ui.blank()

    ui.line(f"  ⚡ Processing: '{text}'...", MUTED)

    start_time = time.monotonic()
    result = await agent.run_turn(text)
    elapsed = time.monotonic() - start_time

    ui.blank()
    if result.reply:
        ui.reply(result.reply)
        ui.muted(f"  [Time: {elapsed:.2f}s | Steps: {result.steps_used}]")

        # Speak reply aloud via Edge-TTS / pyttsx3
        if VOICE_OUTPUT_ENABLED:
            asyncio.create_task(asyncio.to_thread(tts.say, result.reply))
    elif result.error:
        ui.error(f"Error: {result.error}")
        if VOICE_OUTPUT_ENABLED:
            asyncio.create_task(asyncio.to_thread(tts.say, "An error occurred while executing the command, Sir."))

    ui.blank()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
