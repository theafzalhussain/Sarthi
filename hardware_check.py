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
    python hardware_check.py --mic-scan # HAR mic try karo, best batao
    python hardware_check.py --stt-tune # galat suna? best Whisper setting dhoondho
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


# ----------------------------------------------------------------------
#  Voice API wrappers
#
#  Ye thin wrappers isliye hain ki TEST inhe call kar sake.
#
#  Pehle ye code seedha check_mic()/check_speaker() ke andar tha, aur
#  imports function ke andar the. Nateeja: maine galat API naam guess
#  kar liye (`Microphone` instead of `Recorder`, `engine.speak()`
#  instead of `engine.say()`) aur SANDBOX MEIN PAKDA NAHI GAYA, kyunki
#  wahan mic nahi tha to wo code path chala hi nahi.
#
#  User ki asli machine pe crash hua. Ab ye wrappers alag hain, aur
#  tests/test_hardware_check.py inhe hardware ke BINA call karke verify
#  karta hai ki API naam sahi hain.
# ----------------------------------------------------------------------


def open_recorder(device=None):
    """Mic recorder banao. (API: saarthi.voice.Recorder)"""
    from saarthi.voice import AudioConfig, Recorder

    return Recorder(AudioConfig.from_env(), device=device)


def peak_level(recorder, seconds: float = 0.25) -> int:
    """Abhi ka peak level (0-32767). (API: Recorder.peak_level)"""
    return recorder.peak_level(seconds)


def level_bar(peak: int, width: int = 30) -> str:
    """
    Peak ko bar mein badlo — user ko DIKHE ki awaaz aa rahi hai.

        peak     0-300     -> practically silence
        peak   300-1500    -> bahut dheema (Whisper ko sunai nahi dega)
        peak  1500+        -> theek
    """
    filled = min(width, int(width * min(peak, 8000) / 8000))
    bar = ("#" * filled) + ("." * (width - filled))

    if peak < 300:
        verdict = "kuch nahi"
    elif peak < 1500:
        verdict = "bahut dheema"
    elif peak < 4000:
        verdict = "theek"
    else:
        verdict = "accha"

    return f"[{bar}] {peak:>5}  {verdict}"


def record_seconds(recorder, seconds: float):
    """Fixed time ke liye record karo. (API: Recorder.record_fixed)"""
    return recorder.record_fixed(seconds)


def open_stt():
    """Whisper STT banao — model load NAHI karta. (API: WhisperSTT)"""
    from saarthi.voice import WhisperConfig, WhisperSTT

    return WhisperSTT(WhisperConfig.from_env())


def speak_text(engine, text: str) -> bool:
    """
    Awaaz mein bolo. (API: TTSEngine.say — NOT .speak)

    Dhyan: BACKEND pe `speak()` hota hai, ENGINE pe `say()`. Yahi
    confusion thi.
    """
    return engine.say(text)


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

    # KAUNSA mic use ho raha hai — ye batana zaroori hai.
    #
    # Windows pe default aksar "Microsoft Sound Mapper - Input" hota
    # hai (legacy MME wrapper). Usse recording aati hai par bahut
    # dheemi, aur Whisper ko kuch sunai nahi deta. User ko lagta hai
    # voice tuta hua hai, jabki sirf galat device select hai.
    try:
        from saarthi.voice import AudioConfig, describe_device

        config = AudioConfig.from_env()
        say(f"[INFO] Use ho raha hai: {describe_device(config.device)}")

        if config.device is None:
            chosen = describe_device(None).lower()
            if "sound mapper" in chosen or "primary sound" in chosen:
                say(
                    "   Dhyan: ye ek legacy MME device hai — recording "
                    "bahut dheemi aa sakti hai.",
                    "warn",
                )
                say(
                    "   Sahi mic dhoondhne ke liye chala: "
                    "python hardware_check.py --mic-scan",
                    "warn",
                )
    except Exception:  # noqa: BLE001
        pass

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
        recorder = open_recorder()

        # --- LIVE LEVEL METER ---
        # Recording ke BAAD number dikhana kaafi nahi — user ko usi
        # waqt dikhna chahiye ki awaaz register ho rahi hai ya nahi.
        say("")
        say("   Bolte raho — 3 second tak level dikhaunga:", "muted")
        levels = []
        for _ in range(12):
            level = peak_level(recorder, 0.25)
            levels.append(level)
            print(f"      {level_bar(level)}")

        best_live = max(levels) if levels else 0
        if best_live < 300:
            result(
                "Live level",
                False,
                f"peak sirf {best_live} — mic tak awaaz pahunch hi nahi rahi",
            )
            say("   Ye teen cheezein check kar:", "warn")
            say("   1. Windows: Settings > System > Sound > Input — volume badha", "warn")
            say("   2. Mic mute na ho (laptop pe hardware mute key bhi hoti hai)", "warn")
            say("   3. Galat device select hai? chala: "
                "python hardware_check.py --mic-scan", "warn")
        elif best_live < 1500:
            result("Live level", False, f"peak {best_live} — bahut dheema hai")
            say("   Whisper ko itni dheemi awaaz sunai nahi degi.", "warn")
            say("   Mic volume badha, ya --mic-scan se behtar device dhoondh.", "warn")
        else:
            result("Live level", True, f"peak {best_live} — theek hai")

        say("")
        say("   Ab 3 second ke liye bol: \"paytm kholo\"", "muted")
        samples = record_seconds(recorder, 3.0)

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
        stt = open_stt()
        stt.load()

        # transcribe() khud Hinglish correction laga deta hai (PILLAR #1)
        transcript = stt.transcribe(samples)

        result(
            "Transcribe",
            bool(transcript.text and transcript.text.strip()),
            f"suna: {transcript.text!r}",
        )

        # QUALITY SIGNALS — yahi batate hain ki galat kyun suna.
        #
        # Ye pehle nahi dikhte the, isliye "galat suna" ka koi diagnosis
        # nahi tha. avg_logprob confidence batata hai; detected language
        # batata hai ki Whisper ne kaunsi bhasha maani.
        say(
            f"   confidence : logprob {transcript.avg_logprob:.2f}   "
            f"no_speech {transcript.no_speech_prob:.2f}",
            "muted",
        )
        if transcript.language:
            say(
                f"   language   : {transcript.language} "
                f"({transcript.language_probability:.0%} sure)",
                "muted",
            )

        # Confidence kam hai to model chhota hone ka shak
        if transcript.avg_logprob < -0.9 and transcript.text.strip():
            say("")
            say(
                "   Confidence kam hai — model chhota ho sakta hai, ya "
                "bhasha setting galat.",
                "warn",
            )
            say(
                "   Kaunsi setting teri awaaz pe best hai wo MEASURE kar:",
                "warn",
            )
            say("       python hardware_check.py --stt-tune", "warn")

        # Whisper ka RAW output vs correction ke baad — yahi ASR layer
        # ki asli value dikhata hai
        if transcript.raw_text and transcript.raw_text != transcript.text:
            say(f"   Whisper ne suna : {transcript.raw_text!r}", "muted")
            say(f"   Correction baad : {transcript.text!r}", "muted")
        else:
            say("   (correction ki zarurat nahi padi)", "muted")

        if not transcript.is_usable:
            result("Audio quality", False, transcript.reject_reason)
        say(f"   speed: {transcript.speed_ratio:.1f}x realtime", "muted")

    except Exception as exc:  # noqa: BLE001
        result("Transcribe", False, f"{type(exc).__name__}: {exc}")


def scan_mics() -> None:
    """
    HAR input device se record karke batao kaunsa sach mein sunta hai.

    Ye us asli problem ka ilaaj hai jo user ki machine pe mila: 21
    input devices the, aur system default "Microsoft Sound Mapper"
    tha — jisse peak sirf 303 aata tha (practically silence). Asli
    Realtek mic alag index pe tha.

    Guess karne se behtar hai sabko chala ke dekh lena.
    """
    section("Mic scan — kaunsa mic sach mein sunta hai")

    try:
        from saarthi.voice import input_devices, is_audio_available
    except Exception as exc:  # noqa: BLE001
        result("Voice module import", False, str(exc))
        return

    if not is_audio_available():
        result("Mic available", False, "sounddevice / PortAudio nahi hai")
        return

    devices = input_devices()
    if not devices:
        result("Input devices", False, "koi input device nahi mila")
        return

    say(f"{len(devices)} input device milе. Har ek se 1 second record karunga.")
    say("BOLTE RAHO poore scan ke dauraan — warna sab 0 aayega.", "warn")
    say("")
    try:
        input("   Ready ho to Enter dabao (skip: Ctrl+C): ")
    except (EOFError, KeyboardInterrupt):
        say("")
        result("Mic scan", None, "user ne skip kiya")
        return

    results = []
    for device in devices:
        label = f"[{device['index']}] {device['name'][:38]}"
        try:
            recorder = open_recorder(device=device["index"])
            peak = peak_level(recorder, 1.0)
            results.append((peak, device))
            print(f"   {label:<45} {level_bar(peak, width=20)}")
        except Exception as exc:  # noqa: BLE001
            short = str(exc).splitlines()[0][:50]
            print(f"   {label:<45} chal nahi paya — {short}")

    if not results:
        result("Mic scan", False, "koi device se record nahi hua")
        return

    results.sort(key=lambda item: item[0], reverse=True)
    best_peak, best = results[0]

    say("")
    if best_peak < 300:
        result("Koi mic sunta hai", False, f"sabse accha bhi sirf {best_peak} tha")
        say("   Matlab problem device ka nahi hai — mic hi mute hai ya", "warn")
        say("   Windows ne permission nahi di hai. Ye check kar:", "warn")
        say("   - Settings > System > Sound > Input > volume", "warn")
        say("   - Settings > Privacy & security > Microphone > allow apps", "warn")
        say("   - Laptop ka hardware mute key / F-key", "warn")
        return

    result("Sabse accha mic mila", True, f"peak {best_peak}")
    say("")
    if HAS_UI:
        ui.hint(
            f"Ye mic use kar:\n"
            f"    [{best['index']}] {best['name']}\n\n"
            f".env mein ye line daal (NAAM se, index se nahi):\n"
            f"    SAARTHI_MIC_DEVICE={best['name']}\n\n"
            f"Naam se kyun? Index reboot pe ya USB nikaalne pe BADAL\n"
            f"jaata hai, naam usually same rehta hai.\n\n"
            f"Phir dobara chala: python hardware_check.py --mic",
            title="ab ye kar",
        )
    else:
        say(f"Ye .env mein daal: SAARTHI_MIC_DEVICE={best['name']}")

    # Top 3 dikhao — kabhi kabhi doosra option behtar hota hai
    if len(results) > 1:
        say("Top options:", "muted")
        for peak, device in results[:3]:
            say(f"   peak {peak:>5}  [{device['index']}] {device['name']}", "muted")


TUNE_PHRASE = "paytm kholo"


def similarity(got: str, expected: str) -> float:
    """
    Do text kitne match karte hain (0.0 - 1.0).

    stdlib `difflib` use kar rahe hain — koi nayi dependency nahi.
    """
    import difflib
    import re

    def clean(text):
        return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))

    return difflib.SequenceMatcher(None, clean(got), clean(expected)).ratio()


def scan_stt() -> None:
    """
    Kaunsi Whisper setting TERI AWAAZ pe best hai — measure karo.

    KYUN YE BANA:
        User ne "paytm kholo" bola. Audio quality perfect thi (peak
        24087, rms 2940). Par Whisper ne suna:
            "Kya kya ouri website, proper da yaar uca."

        Do shak the: model chhota (base) hai, ya WHISPER_LANGUAGE=en
        Hindi awaaz pe galat map kar raha hai.

        Guess karke .env badalna time waste hai. Ye function EK
        recording pe SAARI settings try karke score deta hai.

    Ek hi model load hota hai aur teen language variants try hote hain
    (transcribe(language=...) override se) — isliye tez hai.
    """
    section("STT tuning — kaunsi setting teri awaaz pe best hai")

    try:
        from saarthi.voice import WhisperConfig, is_audio_available, is_stt_available
        from saarthi.voice.stt import recommend_model_size, total_ram_gb
    except Exception as exc:  # noqa: BLE001
        result("Voice module import", False, str(exc))
        return

    if not is_audio_available():
        result("Mic available", False, "sounddevice / PortAudio nahi hai")
        return
    if not is_stt_available():
        result("faster-whisper", False, "pip install faster-whisper")
        return

    config = WhisperConfig.from_env()
    ram = total_ram_gb()
    suggested = recommend_model_size()

    say(f"[INFO] RAM: {ram:.1f} GB   Tera model: {config.model_size}   "
        f"Suggested: {suggested}")
    say(f"[INFO] Abhi ki language setting: {config.language or 'auto'}")

    if config.model_size != suggested:
        say("")
        say(
            f"   Dhyan: tere RAM pe '{suggested}' chal sakta hai par tu "
            f"'{config.model_size}' use kar raha hai.",
            "warn",
        )
        say(
            "   Chhota model Hinglish pe kamzor hota hai — code-switched "
            "speech mein galtiyan karta hai.",
            "warn",
        )

    say("")
    say(f'Main tujhse bolwaunga: "{TUNE_PHRASE}"', "muted")
    say("Phir har setting pe try karke score dunga.", "muted")
    say("")
    try:
        input(f'   Ready ho to Enter dabao, phir bol "{TUNE_PHRASE}" (skip: Ctrl+C): ')
    except (EOFError, KeyboardInterrupt):
        say("")
        result("STT tune", None, "user ne skip kiya")
        return

    # --- Ek baar record karo, sab variants pe wahi audio use karo ---
    try:
        recorder = open_recorder()
        say(f'   Bol: "{TUNE_PHRASE}" ... (3 second)', "muted")
        samples = record_seconds(recorder, 3.0)
    except Exception as exc:  # noqa: BLE001
        result("Recording", False, f"{type(exc).__name__}: {exc}")
        return

    if samples is None or len(samples) == 0:
        result("Recording", False, "koi audio nahi mila")
        return

    try:
        import numpy as np

        peak = int(abs(samples).max())
    except Exception:  # noqa: BLE001
        peak = 0

    result("Recording", True, f"peak {peak}")
    if peak < 1500:
        say("   Awaaz bahut dheemi hai — pehle --mic-scan chala.", "warn")

    # --- Har language variant try karo (ek hi model load) ---
    say("")
    say("   Model load kar raha hun...", "muted")

    try:
        stt = open_stt()
        stt.load()
    except Exception as exc:  # noqa: BLE001
        result("Model load", False, f"{type(exc).__name__}: {exc}")
        return

    variants = [("en", "en"), ("hi", "hi"), ("auto", None)]
    scores = []

    say("")
    say(f'   Expected: "{TUNE_PHRASE}"', "muted")
    say("")

    for label, language in variants:
        try:
            transcript = stt.transcribe(samples, language=language)
        except Exception as exc:  # noqa: BLE001
            print(f"      language={label:<5} chal nahi paya — {str(exc)[:40]}")
            continue

        raw_score = similarity(transcript.raw_text, TUNE_PHRASE)
        fixed_score = similarity(transcript.text, TUNE_PHRASE)
        best = max(raw_score, fixed_score)
        scores.append((best, label, transcript))

        print(f"      language={label:<5} score {best:.0%}   {transcript.text!r}")
        if transcript.raw_text != transcript.text:
            print(f"         (Whisper ne suna: {transcript.raw_text!r})")

    if not scores:
        result("STT tune", False, "koi variant chala hi nahi")
        return

    scores.sort(key=lambda item: item[0], reverse=True)
    best_score, best_label, best_transcript = scores[0]

    say("")
    if best_score >= 0.75:
        result("Best setting mil gayi", True, f"language={best_label} ({best_score:.0%})")
        lines = [
            f"Ye .env mein set kar:",
            f"    WHISPER_LANGUAGE={best_label}",
        ]
        if config.model_size != suggested:
            lines.append(f"    WHISPER_MODEL={suggested}      # aur accha hoga")
    else:
        result(
            "Koi setting theek nahi chali",
            False,
            f"sabse accha bhi sirf {best_score:.0%} tha",
        )
        lines = [
            "Teeno language settings fail hui. Sabse mumkin wajah:",
            f"MODEL CHHOTA HAI ('{config.model_size}').",
            "",
            f"'{suggested}' try kar (tere {ram:.0f}GB RAM pe chalega):",
            f"    WHISPER_MODEL={suggested}",
            "",
            "Phir dobara chala: python hardware_check.py --stt-tune",
            "",
            "Dhyan: 'small' ~500MB download hoga, 'medium' ~1.5GB.",
            "Ek hi baar download hota hai.",
        ]

    if HAS_UI:
        ui.hint("\n".join(lines), title="ab ye kar")
    else:
        for line in lines:
            say(line)

    say("Saare results:", "muted")
    for score, label, transcript in scores:
        say(f"   {score:>4.0%}  language={label:<5} {transcript.text!r}", "muted")


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
        speak_text(engine, "Namaste bhai, main SAARTHI hun. Awaaz sunai de rahi hai?")
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

    only = args & {"--mic", "--speaker", "--phone", "--browser", "--keys",
                   "--mic-scan", "--stt-tune"}
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

    if "--mic-scan" in only:
        scan_mics()

    if "--stt-tune" in only:
        scan_stt()

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
