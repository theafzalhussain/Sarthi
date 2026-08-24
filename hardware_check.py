#!/usr/bin/env python3
"""
SAARTHI — Hardware diagnostic.

YE SCRIPT KIS LIYE HAI:

    Phase 1 aur 2 ka code sandbox mein bana tha jahan MIC NAHI THA,
    SPEAKER NAHI THA, PHONE NAHI THA. Logic sab verify ho chuka hai
    (195 automated tests), par asli hardware pe kabhi chala nahi.

    Ye script tere hardware ko check karti hai aur ek REPORT banati
    hai jo tu copy-paste karke dev/AI ko de sakta hai. Wo report se
    exact bug pakad lega.

CHALANE KA TAREEKA:

    python hardware_check.py            # sab check karo
    python hardware_check.py --mic      # sirf mic
    python hardware_check.py --phone    # sirf phone (ADB)
    python hardware_check.py --speaker  # sirf awaaz
    python hardware_check.py --save     # report file mein bhi save karo

YE SCRIPT SAFE HAI:
    - Kuch install nahi karti
    - Koi file delete nahi karti
    - Phone pe koi tap nahi karti (sirf connection check)
    - Tere API keys print NAHI karti (sirf "mil gayi / nahi mili")
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

REPORT: list[str] = []


# ----------------------------------------------------------------------
#  Output helpers
# ----------------------------------------------------------------------

try:
    from saarthi.ui import ERR, MUTED, OK, TEXT, WARN, Ui

    ui = Ui()
    HAS_UI = True
except Exception:  # noqa: BLE001 — UI na chale to bhi diagnostic chalna chahiye
    HAS_UI = False
    ui = None
    OK = WARN = ERR = TEXT = MUTED = ""


def say(text: str = "", kind: str = "text") -> None:
    """Screen pe dikhao AUR report mein rakho."""
    REPORT.append(text)

    if not HAS_UI:
        print(text)
        return

    if kind == "ok":
        ui.success(text[3:] if text.startswith("   ") else text)
    elif kind == "warn":
        ui.warn(text)
    elif kind == "fail":
        ui.error(text)
    elif kind == "muted":
        ui.muted(text)
    elif kind == "blank":
        ui.blank()
    else:
        ui.info(text)


def section(title: str) -> None:
    REPORT.append("")
    REPORT.append(f"### {title}")
    if HAS_UI:
        ui.blank()
        ui.section(title)
    else:
        print(f"\n=== {title} ===")


def result(label: str, ok: bool | None, detail: str = "") -> None:
    """
    Ek check ka nateeja.

    ok=None matlab "pata nahi chala" — ye FAIL se alag hai. Imaandaari
    zaroori hai: jo verify nahi kar paye usko pass mat bolo.
    """
    mark = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    say(line, {True: "ok", False: "fail", None: "muted"}[ok])


# ----------------------------------------------------------------------
#  1. System
# ----------------------------------------------------------------------


def check_system() -> None:
    section("1  System")

    version = sys.version_info
    py_ok = version >= (3, 9)
    result(
        "Python 3.9+",
        py_ok,
        f"{version.major}.{version.minor}.{version.micro}",
    )
    if not py_ok:
        say("   -> Python 3.9 ya naya chahiye. python.org se update kar.", "warn")

    say(f"[INFO] OS: {platform.system()} {platform.release()} ({platform.machine()})")

    # RAM — Whisper model size isi pe depend karta hai
    try:
        from saarthi.voice import recommend_model_size

        say(f"[INFO] Tere RAM ke hisaab se Whisper model: {recommend_model_size()}")
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------
#  2. Install
# ----------------------------------------------------------------------


def check_install() -> None:
    section("2  Install")

    core = {
        "httpx": "LLM API calls",
        "dotenv": ".env padhne ke liye",
        "rich": "terminal look",
        "bs4": "HTML parse (web search)",
    }
    for module, why in core.items():
        try:
            __import__(module)
            result(f"{module}", True, why)
        except ImportError:
            result(f"{module}", False, f"{why} — pip install -r requirements.txt")

    optional = {
        "faster_whisper": "voice sunna",
        "sounddevice": "microphone",
        "numpy": "audio math",
        "playwright": "browser control",
        "pyautogui": "desktop mouse/keyboard",
        "pvporcupine": "wake word ('jarvis')",
    }
    for module, why in optional.items():
        try:
            __import__(module)
            result(f"{module} (optional)", True, why)
        except ImportError:
            result(f"{module} (optional)", None, f"nahi hai — {why} kaam nahi karega")


# ----------------------------------------------------------------------
#  3. Keys — VALUE KABHI PRINT NAHI KARTE
# ----------------------------------------------------------------------


def check_keys() -> None:
    section("3  API keys")
    say("Keys ki VALUE print nahi hoti — sirf mili ya nahi.", "muted")

    try:
        from saarthi.config import Settings

        settings = Settings.load()
    except Exception as exc:  # noqa: BLE001
        result("Settings load", False, str(exc))
        return

    available = [p.name for p in settings.available_providers]
    result(
        "Kam se kam ek key hai",
        bool(available),
        f"{len(available)} providers ready: {', '.join(available)}" if available
        else "koi key nahi — .env mein daal",
    )

    if not available:
        say("   -> https://build.nvidia.com se free key le (4 models milte hain)", "warn")
        return

    say(f"[INFO] Provider order: {' -> '.join(settings.provider_order)}")

    if settings.order_is_explicit and settings.order_missing:
        result(
            "Provider order up-to-date",
            False,
            f".env mein SAARTHI_PROVIDER_ORDER likha hai par usme "
            f"{', '.join(settings.order_missing)} nahi hain — wo aakhir mein "
            f"jaayenge. Us line ko comment kar de.",
        )
    else:
        result("Provider order up-to-date", True)

    say(f"[INFO] Reply language: {settings.language}")
    say(f"[INFO] Browser mode: {settings.browser_mode}")
    say(f"[INFO] Max steps: {settings.max_steps}")


# ----------------------------------------------------------------------
#  4. Microphone
# ----------------------------------------------------------------------


def check_mic(interactive: bool = True) -> None:
    section("4  Microphone")

    try:
        from saarthi.voice import audio_setup_help, is_audio_available, list_input_devices
    except Exception as exc:  # noqa: BLE001
        result("Voice module import", False, str(exc))
        return

    if not is_audio_available():
        result("Mic available", False, "sounddevice / PortAudio nahi hai")
        say("")
        for line in audio_setup_help().splitlines():
            say(f"   {line}", "muted")
        return

    devices = list_input_devices()
    result("Mic available", bool(devices), f"{len(devices)} input device")
    for device in devices[:5]:
        say(f"   - {device}", "muted")

    if not interactive:
        result("Asli recording test", None, "--mic ke bina skip")
        return

    # --- Asli recording ---
    say("")
    say("Ab ASLI RECORDING test karenge — 3 second bolna hai.", "warn")
    try:
        input("   Ready ho to Enter dabao (skip karne ke liye Ctrl+C): ")
    except (EOFError, KeyboardInterrupt):
        say("")
        result("Asli recording test", None, "user ne skip kiya")
        return

    try:
        from saarthi.voice.audio import AudioConfig, Microphone

        mic = Microphone(AudioConfig())
        say("   Bol: \"paytm kholo\" ... (3 second)", "muted")
        samples = mic.record_seconds(3.0)

        if samples is None or len(samples) == 0:
            result("Recording", False, "koi audio nahi mila")
            return

        # Awaaz aayi ya sirf silence?
        try:
            import numpy as np

            peak = int(np.abs(samples).max())
            rms = float(np.sqrt(np.mean(samples.astype("float64") ** 2)))
        except Exception:  # noqa: BLE001
            peak = max(abs(int(s)) for s in samples[:5000])
            rms = 0.0

        result("Recording", True, f"{len(samples)} samples, peak={peak}")

        # int16 range 0-32767. 500 se kam matlab practically silence.
        if peak < 500:
            result(
                "Awaaz aayi",
                False,
                f"peak sirf {peak} — mic mute hai ya galat device select hai",
            )
            say("   -> System settings mein mic unmute kar, permission de", "warn")
        else:
            result("Awaaz aayi", True, f"peak={peak}, rms={rms:.0f}")

    except KeyboardInterrupt:
        result("Recording", None, "user ne rok diya")
        return
    except Exception as exc:  # noqa: BLE001
        result("Recording", False, f"{type(exc).__name__}: {exc}")
        return

    # --- Transcribe ---
    try:
        from saarthi.voice import is_stt_available
    except Exception:  # noqa: BLE001
        return

    if not is_stt_available():
        result("Transcribe", None, "faster-whisper nahi hai (pip install faster-whisper)")
        return

    say("")
    say("   Whisper model load kar raha hun (pehli baar download hoga)...", "muted")
    try:
        from saarthi.voice.stt import SpeechToText, STTConfig

        stt = SpeechToText(STTConfig.from_env())
        stt.load()
        text = stt.transcribe(samples)
        result("Transcribe", bool(text and text.strip()), f"suna: {text!r}")

        if text and text.strip():
            from saarthi.voice.hinglish_asr import correct_transcript

            fixed = correct_transcript(text)
            if fixed.was_changed:
                say(f"   Hinglish correction: {fixed.explain()}", "muted")
            else:
                say("   (koi correction ki zarurat nahi padi)", "muted")
    except Exception as exc:  # noqa: BLE001
        result("Transcribe", False, f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------
#  5. Speaker
# ----------------------------------------------------------------------


def check_speaker(interactive: bool = True) -> None:
    section("5  Speaker (TTS)")

    try:
        from saarthi.voice.tts import TTSEngine
    except Exception as exc:  # noqa: BLE001
        result("TTS module import", False, str(exc))
        return

    for name, available, quality in TTSEngine.available_backends():
        result(f"backend: {name}", available if available else None, quality)

    engine = TTSEngine()
    result(
        "Koi awaaz available hai",
        engine.has_voice,
        f"chuna gaya: {engine.backend.name}",
    )

    if not engine.has_voice:
        say("   -> Linux: sudo apt install espeak-ng", "warn")
        say("   -> Windows: pip install pyttsx3", "warn")
        say("   -> macOS: 'say' built-in hai, kuch nahi chahiye", "warn")
        return

    if not interactive:
        result("Asli awaaz test", None, "--speaker ke bina skip")
        return

    say("")
    try:
        input("   Awaaz test karne ke liye Enter (skip: Ctrl+C): ")
    except (EOFError, KeyboardInterrupt):
        say("")
        result("Asli awaaz test", None, "user ne skip kiya")
        return

    try:
        engine.speak("Namaste bhai, main SAARTHI hun. Awaaz sunai de rahi hai?")
        say("")
        answer = input("   Awaaz SUNAI DI? (haan/nahi): ").strip().lower()
        heard = answer.startswith(("h", "y"))
        result("Awaaz sunai di", heard, answer or "(khali jawab)")
        if not heard:
            say("   -> Volume check kar, aur output device sahi select kar", "warn")
    except KeyboardInterrupt:
        result("Asli awaaz test", None, "user ne rok diya")
    except Exception as exc:  # noqa: BLE001
        result("Awaaz bajana", False, f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------
#  6. Phone (ADB)
# ----------------------------------------------------------------------


def check_phone() -> None:
    section("6  Phone (ADB)")

    try:
        from saarthi.config import settings as live_settings

        adb_path = live_settings.adb_path
    except Exception:  # noqa: BLE001
        adb_path = "adb"

    binary = shutil.which(adb_path)
    result("adb installed", bool(binary), binary or f"'{adb_path}' PATH mein nahi mila")

    if not binary:
        say("   -> Android Platform Tools download kar:", "warn")
        say("      https://developer.android.com/tools/releases/platform-tools", "muted")
        say("   -> Extract karke folder ko PATH mein daal", "muted")
        return

    try:
        proc = subprocess.run(
            [binary, "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        result("adb devices", False, "20 second mein jawab nahi aaya")
        return
    except Exception as exc:  # noqa: BLE001
        result("adb devices", False, f"{type(exc).__name__}: {exc}")
        return

    output = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    devices = [
        ln for ln in lines
        if "\tdevice" in ln or (" device " in ln and "List of devices" not in ln)
    ]
    unauthorized = [ln for ln in lines if "unauthorized" in ln]
    offline = [ln for ln in lines if "offline" in ln]

    if devices:
        result("Phone connected", True, f"{len(devices)} device")
        for line in devices:
            say(f"   {line}", "muted")
    elif unauthorized:
        result("Phone connected", False, "device UNAUTHORIZED hai")
        say("   -> Phone pe 'Allow USB debugging' popup aayega, Allow dabao", "warn")
        say("   -> Na aaye to: Developer options > Revoke USB debugging", "warn")
    elif offline:
        result("Phone connected", False, "device OFFLINE hai")
        say("   -> Cable nikaal ke dobara laga, ya phone restart kar", "warn")
    else:
        result("Phone connected", False, "koi device nahi mila")
        say("   1. Settings > About phone > Build number pe 7 baar tap", "warn")
        say("   2. Settings > Developer options > USB Debugging ON", "warn")
        say("   3. USB cable laga (charging-only cable se kaam nahi hoga)", "warn")
        say("   4. Phone pe 'Allow' dabao", "warn")
        return

    if not devices:
        return

    # --- Read-only checks. Koi tap nahi. ---
    def adb(*args, timeout=20):
        try:
            proc = subprocess.run(
                [binary, "shell", *args], capture_output=True, text=True, timeout=timeout
            )
            return (proc.stdout or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    model = adb("getprop", "ro.product.model")
    android = adb("getprop", "ro.build.version.release")
    result("Device info padha", bool(model), f"{model} (Android {android})")

    size = adb("wm", "size")
    result("Screen size padha", bool(size), size)

    ui_dump = adb("uiautomator", "dump", "/dev/tty", timeout=30)
    ui_ok = "<hierarchy" in ui_dump or "<node" in ui_dump
    result(
        "Screen padh sakte hain (ui_tree)",
        ui_ok,
        f"{len(ui_dump)} chars" if ui_ok else "uiautomator dump khali aaya",
    )
    if not ui_ok:
        say("   -> Ye zaroori hai. Iske bina text_pe_tap aur self-healing", "warn")
        say("      kaam nahi karenge (sirf blind coordinates bachenge).", "warn")

    say("")
    say("Dhyan: ye script phone pe KOI TAP nahi karti — sirf padhti hai.", "muted")


# ----------------------------------------------------------------------
#  7. Browser
# ----------------------------------------------------------------------


def check_browser() -> None:
    section("7  Browser")

    try:
        from saarthi.devices.browser import HAS_PLAYWRIGHT, PLAYWRIGHT_ERROR
    except Exception as exc:  # noqa: BLE001
        result("Browser module import", False, str(exc))
        return

    result(
        "playwright installed",
        HAS_PLAYWRIGHT,
        PLAYWRIGHT_ERROR or "ok" if not HAS_PLAYWRIGHT else "ok",
    )
    if not HAS_PLAYWRIGHT:
        say("   -> pip install playwright && playwright install chromium", "warn")
        return

    # Chromium download hua hai?
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        result("chromium available", "chromium" in combined.lower(), "dry-run ok")
    except Exception:  # noqa: BLE001
        result("chromium available", None, "check nahi kar paya")

    say("   -> Asli browser test: python cli.py, phir bol \"google kholo\"", "muted")


# ----------------------------------------------------------------------
#  Main
# ----------------------------------------------------------------------


def print_summary() -> int:
    section("Summary")

    passed = sum(1 for line in REPORT if line.startswith("[PASS]"))
    failed = [line for line in REPORT if line.startswith("[FAIL]")]
    skipped = sum(1 for line in REPORT if line.startswith("[SKIP]"))

    say(f"PASS: {passed}   FAIL: {len(failed)}   SKIP: {skipped}")

    if failed:
        say("")
        say("Ye theek karna hai:", "warn")
        for line in failed:
            say(f"   {line}", "fail")

    say("")
    if HAS_UI:
        ui.hint(
            "Is poori output ko COPY karke dev/AI ko bhej de.\n"
            "Usse exact bug pakad mein aa jaayega.\n\n"
            "Ya file mein save kar:  python hardware_check.py --save\n\n"
            "Dhyan: ye report mein teri API keys NAHI hain — safe hai.",
            title="ab kya karna hai",
        )
    else:
        say("Is output ko copy karke dev/AI ko bhej de.")

    return 1 if failed else 0


def main() -> int:
    args = set(sys.argv[1:])

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    only = args & {"--mic", "--speaker", "--phone", "--browser", "--keys"}
    run_all = not only

    if HAS_UI:
        try:
            from saarthi import __version__
        except Exception:  # noqa: BLE001
            __version__ = "?"
        ui.banner(__version__, "Hardware diagnostic", mode="hardware check")
    else:
        print("SAARTHI — hardware check\n")

    say("Ye script kuch install nahi karti, kuch delete nahi karti,", "muted")
    say("phone pe koi tap nahi karti, aur API keys print nahi karti.", "muted")

    if run_all or "--keys" in only:
        check_system()
        check_install()
        check_keys()

    if run_all or "--mic" in only:
        check_mic(interactive=("--mic" in only) or run_all)

    if run_all or "--speaker" in only:
        check_speaker(interactive=("--speaker" in only) or run_all)

    if run_all or "--phone" in only:
        check_phone()

    if run_all or "--browser" in only:
        check_browser()

    code = print_summary()

    if "--save" in args:
        out = ROOT / "hardware_report.txt"
        out.write_text("\n".join(REPORT), encoding="utf-8")
        say(f"Report save ho gayi: {out}", "ok")

    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nRok diya.\n")
        sys.exit(130)
