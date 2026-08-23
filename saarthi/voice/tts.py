"""
Text-to-Speech — SAARTHI ki awaaz.

Sab backends FREE aur OFFLINE hain:

    Backend    Quality      Setup                    Note
    --------   ----------   ----------------------   ---------------------
    piper      bahut acchi  voice model download     recommended
    espeak     robotic      apt install espeak-ng    halka, hamesha chalta
    say        acchi        macOS mein built-in      Mac users
    pyttsx3    theek        pip install pyttsx3      cross-platform
    null       (text)       kuch nahi                fallback — print karta hai

DESIGN RULE:
    TTS na ho to bhi agent CHALTA RAHEGA. NullTTS jawab print kar deta
    hai. Awaaz na aane se pura agent band nahi hona chahiye — ye ek
    "nice to have" hai, "must have" nahi.


HINGLISH TTS KA SACH (imaandaar baat):

    Hamara text ROMAN Hinglish hota hai: "paytm khol diya, 2500 ka bill"

    Options:
      (a) English voice se padhwao
          -> samajh aata hai, thoda accent lagta hai
          -> DEFAULT yahi hai, kyunki reliable hai

      (b) Hindi voice se padhwao
          -> Hindi voices Devanagari expect karti hain
          -> Roman text Hindi voice ko theek se nahi padha jaata

    Perfect Hinglish TTS ke liye roman->Devanagari transliteration
    chahiye hoga, jo lossy hai. Abhi (a) use kar rahe hain — kaam
    chal jaata hai. Baad mein improve kar sakte hain.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .audio import play_wav

log = logging.getLogger("saarthi.voice.tts")


# ======================================================================
#  Text prep — bolne se pehle text saaf karo
# ======================================================================

# Emoji aur symbols — TTS inko "black circle" jaisa padh deta hai
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F9FF"  # symbols, emoticons, pictographs
    "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000027BF"  # misc symbols, dingbats
    "\U0001F000-\U0001F0FF"
    "\U00002190-\U000021FF"  # arrows
    "\U00002B00-\U00002BFF"
    "\uFE0F"                 # variation selector
    "\u200D"                 # zero width joiner
    "]+",
    flags=re.UNICODE,
)

# Symbols ko bolne layak shabd banao
SYMBOL_WORDS: list[tuple[str, str]] = [
    (r"₹\s*", "rupay "),
    (r"\$\s*", "dollar "),
    (r"\s*%", " percent"),
    (r"\s*&\s*", " and "),
    (r"\s*@\s*", " at "),
    (r"\s*\+\s*", " plus "),
    (r"\s*=\s*", " barabar "),
    (r"\s*->\s*", " se "),
    (r"\s*/\s*", " slash "),
]


def prepare_text_for_speech(text: str, max_chars: int = 500) -> str:
    """
    Text ko bolne layak banao.

    Kaam:
      - Markdown hatao (**bold**, `code`, [link](url), # heading)
      - Emoji hatao
      - Symbols ko shabd banao (₹ -> rupay)
      - Bullet points ko natural banao
      - Bahut lamba text kaato (pura webpage nahi sunana)

    Ye function PURE LOGIC hai — test karna aasaan hai.

    >>> prepare_text_for_speech("**Ho gaya!** ₹2500 ka bill bhar diya 🎉")
    'Ho gaya! rupay 2500 ka bill bhar diya'
    """
    if not text:
        return ""

    working = text

    # --- Markdown ---
    # Code blocks pura hata do — code bolna bekaar hai
    working = re.sub(r"```[\s\S]*?```", " ", working)
    working = re.sub(r"`([^`]*)`", r"\1", working)
    # Links: [text](url) -> text
    working = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", working)
    # Bold/italic
    working = re.sub(r"\*\*([^*]+)\*\*", r"\1", working)
    working = re.sub(r"\*([^*]+)\*", r"\1", working)
    working = re.sub(r"__([^_]+)__", r"\1", working)
    # Headings
    working = re.sub(r"^#{1,6}\s*", "", working, flags=re.MULTILINE)
    # Horizontal rules
    working = re.sub(r"^\s*[-*_]{3,}\s*$", " ", working, flags=re.MULTILINE)
    # Table pipes
    working = working.replace("|", " ")

    # --- Bullets -> plain lines ---
    # Marker hata dete hain (comma nahi lagate) — newline khud
    # ". " ban jaata hai, jisse natural pause aata hai.
    # Comma lagane se ". ," jaisa kachra banta tha.
    working = re.sub(r"^\s*[-*•]\s+", "", working, flags=re.MULTILINE)
    working = re.sub(r"^\s*\d+[.)]\s+", "", working, flags=re.MULTILINE)

    # --- Emoji ---
    working = _EMOJI_PATTERN.sub(" ", working)

    # --- Symbols -> words ---
    for pattern, replacement in SYMBOL_WORDS:
        working = re.sub(pattern, replacement, working)

    # --- Whitespace saaf ---
    working = re.sub(r"\n{2,}", ". ", working)
    working = working.replace("\n", ". ")
    working = re.sub(r"\s+", " ", working)

    # --- Punctuation saaf ---
    # "!!!" / "???" ko single karo — TTS inko weird padhta hai
    working = re.sub(r"([!?])\1{1,}", r"\1", working)
    # ".,", ",.", "..", ",," jaisa kachra
    working = re.sub(r"[.,]{2,}", ".", working)
    working = re.sub(r"\.\s*,", ".", working)
    working = re.sub(r",\s*\.", ".", working)
    # "!." / "?." / ":." -> pehla punctuation hi rakho.
    # Ye newline->". " conversion se banta hai aur sunne mein bura lagta hai.
    working = re.sub(r"([!?:;])\s*\.", r"\1", working)
    # Punctuation se pehle space
    working = re.sub(r"\s+([.,!?])", r"\1", working)
    # Punctuation ke baad space na ho to daal do
    working = re.sub(r"([.,!?])([A-Za-z])", r"\1 \2", working)

    working = re.sub(r"\s+", " ", working).strip(" ,.")

    # --- Length cap ---
    if len(working) > max_chars:
        cut = working[:max_chars]
        # Sentence boundary pe kaato, warna word boundary pe
        for sep in (". ", "! ", "? "):
            index = cut.rfind(sep)
            if index > max_chars * 0.5:
                return cut[: index + 1].strip()
        return cut.rsplit(" ", 1)[0].strip() + "..."

    return working.strip()


# ======================================================================
#  Backend abstraction
# ======================================================================


@dataclass
class TTSConfig:
    """TTS ki settings."""

    # piper | espeak | say | pyttsx3 | null | auto
    backend: str = "auto"

    # Piper ka voice model (.onnx file ka path)
    piper_model: str | None = None

    # espeak voice: en-in = Indian English (Hinglish ke liye best)
    espeak_voice: str = "en-in"

    # Bolne ki speed
    speed: float = 1.0

    # Ek baar mein max kitne characters bolna
    max_chars: int = 500

    @classmethod
    def from_env(cls) -> "TTSConfig":
        def _float(key: str, default: float) -> float:
            raw = os.getenv(key)
            try:
                return float(raw) if raw else default
            except ValueError:
                return default

        return cls(
            backend=os.getenv("TTS_BACKEND", "auto").strip().lower(),
            piper_model=os.getenv("PIPER_MODEL") or None,
            espeak_voice=os.getenv("ESPEAK_VOICE", "en-in").strip(),
            speed=_float("TTS_SPEED", 1.0),
            max_chars=int(_float("TTS_MAX_CHARS", 500)),
        )


class TTSBackend(ABC):
    """Ek TTS backend."""

    name: str = "unknown"
    quality: str = "unknown"

    def __init__(self, config: TTSConfig | None = None):
        self.config = config or TTSConfig()

    @abstractmethod
    def is_available(self) -> bool:
        """Ye backend abhi use ho sakta hai?"""
        raise NotImplementedError

    @abstractmethod
    def speak(self, text: str) -> bool:
        """Text bolo. Returns: bola ya nahi."""
        raise NotImplementedError

    def synthesize_to_file(self, text: str, path: str | Path) -> Path | None:
        """
        Audio file banao (bajao nahi).

        Sab backends support nahi karte — None return karte hain.
        """
        return None

    def setup_help(self) -> str:
        return f"{self.name} available nahi hai."

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} available={self.is_available()}>"


# ======================================================================
#  1. Piper — best quality, offline
# ======================================================================

# Free voice models yahan se milte hain
PIPER_VOICES_URL = "https://huggingface.co/rhasspy/piper-voices"

# Ye voices Hinglish ke liye theek hain
PIPER_RECOMMENDED = {
    "en_US-amy-medium": "English female, saaf — Hinglish ke liye theek",
    "en_GB-alan-medium": "English male",
    "hi_IN-pratham-medium": "Hindi male (Devanagari text ke liye)",
}


class PiperTTS(TTSBackend):
    """Piper — offline neural TTS. Sabse acchi quality."""

    name = "piper"
    quality = "bahut acchi"

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._voice = None
        self._checked = False
        self._error = ""

    # ------------------------------------------------------------------

    def _find_model(self) -> Path | None:
        """Voice model dhoondo."""
        # 1. Config se
        if self.config.piper_model:
            path = Path(self.config.piper_model).expanduser()
            if path.exists():
                return path
            self._error = f"PIPER_MODEL set hai par file nahi mili: {path}"
            return None

        # 2. Standard jagahon pe dhoondo
        search_dirs = [
            Path.home() / ".local" / "share" / "piper" / "voices",
            Path.home() / ".cache" / "piper",
            Path("data") / "voices",
            Path("voices"),
        ]
        for directory in search_dirs:
            if not directory.exists():
                continue
            models = sorted(directory.glob("*.onnx"))
            if models:
                return models[0]

        return None

    def _load(self) -> bool:
        """Voice load karo (lazy)."""
        if self._voice is not None:
            return True
        if self._checked:
            return False

        self._checked = True

        try:
            from piper import PiperVoice
        except ImportError as exc:
            self._error = f"piper-tts install nahi hai ({exc})"
            return False

        model_path = self._find_model()
        if model_path is None:
            if not self._error:
                self._error = "Koi Piper voice model (.onnx) nahi mila"
            return False

        try:
            self._voice = PiperVoice.load(str(model_path))
            log.info("Piper voice load ho gayi: %s", model_path.name)
            return True
        except Exception as exc:  # noqa: BLE001
            self._error = f"Piper voice load nahi hui: {exc}"
            return False

    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return self._load()

    def synthesize_to_file(self, text: str, path: str | Path) -> Path | None:
        if not self._load():
            return None

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with wave.open(str(out_path), "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)
            return out_path
        except Exception as exc:  # noqa: BLE001
            log.warning("Piper synthesis fail: %s", exc)
            return None

    def speak(self, text: str) -> bool:
        if not text:
            return False

        temp_dir = Path(tempfile.gettempdir())
        wav_path = temp_dir / "saarthi_tts.wav"

        result = self.synthesize_to_file(text, wav_path)
        if result is None:
            return False

        try:
            return play_wav(result)
        finally:
            wav_path.unlink(missing_ok=True)

    def setup_help(self) -> str:
        lines = ["Piper TTS setup:"]
        lines.append("")
        lines.append("  1. pip install piper-tts")
        lines.append("")
        lines.append("  2. Ek voice model download kar (free):")
        lines.append(f"       {PIPER_VOICES_URL}")
        lines.append("")
        lines.append("     Recommended:")
        for voice, note in PIPER_RECOMMENDED.items():
            lines.append(f"       {voice}")
            lines.append(f"           {note}")
        lines.append("")
        lines.append("  3. .onnx (aur .onnx.json) file yahan rakh:")
        lines.append("       ~/.local/share/piper/voices/")
        lines.append("     ya .env mein path de:")
        lines.append("       PIPER_MODEL=/path/to/voice.onnx")
        if self._error:
            lines.append("")
            lines.append(f"  Abhi ka error: {self._error}")
        return "\n".join(lines)


# ======================================================================
#  2. espeak-ng — halka, hamesha chalta hai
# ======================================================================


class EspeakTTS(TTSBackend):
    """espeak-ng — robotic awaaz, par bahut halka aur reliable."""

    name = "espeak"
    quality = "robotic par samajh aata hai"

    def _binary(self) -> str | None:
        for candidate in ("espeak-ng", "espeak"):
            if shutil.which(candidate):
                return candidate
        return None

    def is_available(self) -> bool:
        return self._binary() is not None

    def _build_command(self, text: str, out_file: str | None = None) -> list[str]:
        binary = self._binary() or "espeak-ng"
        # espeak ki speed words-per-minute mein hoti hai (default 175)
        wpm = max(80, min(int(175 * self.config.speed), 400))
        command = [binary, "-v", self.config.espeak_voice, "-s", str(wpm)]
        if out_file:
            command += ["-w", out_file]
        command.append(text)
        return command

    def speak(self, text: str) -> bool:
        if not text or not self.is_available():
            return False
        try:
            subprocess.run(
                self._build_command(text),
                check=True,
                capture_output=True,
                timeout=180,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("espeak fail: %s", exc)
            return False

    def synthesize_to_file(self, text: str, path: str | Path) -> Path | None:
        if not text or not self.is_available():
            return None
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                self._build_command(text, str(out_path)),
                check=True,
                capture_output=True,
                timeout=180,
            )
            return out_path if out_path.exists() else None
        except Exception as exc:  # noqa: BLE001
            log.warning("espeak file synthesis fail: %s", exc)
            return None

    def setup_help(self) -> str:
        return (
            "espeak-ng install kar:\n"
            "    Ubuntu/Debian : sudo apt install espeak-ng\n"
            "    Fedora        : sudo dnf install espeak-ng\n"
            "    macOS         : brew install espeak-ng\n"
            "    Windows       : https://github.com/espeak-ng/espeak-ng/releases\n"
            "\n"
            "  Bahut halka hai (~10MB) aur Indian English voice bhi hai (en-in)."
        )


# ======================================================================
#  3. macOS say
# ======================================================================


class MacSayTTS(TTSBackend):
    """macOS ka built-in `say` — Mac pe kuch install nahi karna."""

    name = "say"
    quality = "acchi"

    def is_available(self) -> bool:
        return sys.platform == "darwin" and shutil.which("say") is not None

    def speak(self, text: str) -> bool:
        if not text or not self.is_available():
            return False
        # macOS say ki rate words-per-minute hai
        rate = max(100, min(int(180 * self.config.speed), 400))
        try:
            subprocess.run(
                ["say", "-r", str(rate), text],
                check=True,
                capture_output=True,
                timeout=180,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("say fail: %s", exc)
            return False

    def setup_help(self) -> str:
        return "macOS `say` sirf Mac pe chalta hai."


# ======================================================================
#  4. pyttsx3 — cross-platform
# ======================================================================


class Pyttsx3TTS(TTSBackend):
    """pyttsx3 — Windows/Linux/Mac, system voices use karta hai."""

    name = "pyttsx3"
    quality = "theek"

    def __init__(self, config: TTSConfig | None = None):
        super().__init__(config)
        self._checked = False
        self._works = False

    def is_available(self) -> bool:
        if self._checked:
            return self._works
        self._checked = True
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.stop()
            self._works = True
        except Exception as exc:  # noqa: BLE001
            log.debug("pyttsx3 available nahi: %s", exc)
            self._works = False
        return self._works

    def speak(self, text: str) -> bool:
        if not text or not self.is_available():
            return False
        try:
            import pyttsx3

            engine = pyttsx3.init()
            try:
                current = engine.getProperty("rate") or 200
                engine.setProperty("rate", int(current * self.config.speed))
            except Exception:  # noqa: BLE001
                pass
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("pyttsx3 fail: %s", exc)
            return False

    def setup_help(self) -> str:
        return "pip install pyttsx3"


# ======================================================================
#  5. Null — hamesha chalta hai (fallback)
# ======================================================================


class NullTTS(TTSBackend):
    """
    Awaaz nahi, sirf print.

    Ye ZAROORI hai: TTS setup na ho to bhi agent kaam karta rahe.
    Awaaz "nice to have" hai, agent ki zaroorat nahi.
    """

    name = "null"
    quality = "koi awaaz nahi (text print hota hai)"

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> bool:
        if text:
            print(f"  [awaaz nahi hai, ye bolna tha] {text}")
        return True

    def setup_help(self) -> str:
        return "Ye fallback hai — hamesha chalta hai."


# ======================================================================
#  Engine — best backend chuno
# ======================================================================

# Kis order mein try karna hai (pehla = pehli choice)
BACKEND_ORDER: list[type[TTSBackend]] = [
    PiperTTS,      # best quality
    MacSayTTS,     # Mac pe built-in, acchi quality
    EspeakTTS,     # halka, reliable
    Pyttsx3TTS,    # cross-platform
    NullTTS,       # hamesha chalta hai
]

BACKENDS_BY_NAME: dict[str, type[TTSBackend]] = {
    cls.name: cls for cls in BACKEND_ORDER
}


class TTSEngine:
    """
    SAARTHI ki awaaz.

    Best available backend khud chun leta hai. Kuch bhi na mile to
    NullTTS text print kar deta hai — agent kabhi nahi rukta.

    Use:
        tts = TTSEngine()
        tts.say("Paytm khol diya bhai")
    """

    def __init__(self, config: TTSConfig | None = None):
        self.config = config or TTSConfig()
        self._backend: TTSBackend | None = None

    # ------------------------------------------------------------------

    def _select_backend(self) -> TTSBackend:
        """Best backend chuno."""
        requested = (self.config.backend or "auto").lower()

        # User ne specific backend maanga
        if requested != "auto":
            backend_class = BACKENDS_BY_NAME.get(requested)
            if backend_class is None:
                log.warning(
                    "TTS_BACKEND '%s' unknown hai. Available: %s",
                    requested,
                    ", ".join(BACKENDS_BY_NAME),
                )
            else:
                backend = backend_class(self.config)
                if backend.is_available():
                    return backend
                log.warning(
                    "TTS backend '%s' available nahi hai, auto pe ja raha hun.\n%s",
                    requested,
                    backend.setup_help(),
                )

        # Auto — order mein try karo
        for backend_class in BACKEND_ORDER:
            backend = backend_class(self.config)
            try:
                if backend.is_available():
                    log.info("TTS backend chuna gaya: %s", backend.name)
                    return backend
            except Exception as exc:  # noqa: BLE001
                log.debug("%s check fail: %s", backend_class.__name__, exc)

        return NullTTS(self.config)

    @property
    def backend(self) -> TTSBackend:
        """Current backend (lazy select)."""
        if self._backend is None:
            self._backend = self._select_backend()
        return self._backend

    @property
    def has_voice(self) -> bool:
        """Asli awaaz hai (ya sirf print ho raha hai)?"""
        return self.backend.name != "null"

    # ------------------------------------------------------------------

    def say(self, text: str, prepare: bool = True) -> bool:
        """
        Bolo.

        Args:
            text: Kya bolna hai (markdown/emoji chalega, saaf ho jaayega)
            prepare: Text clean karna hai?
        """
        if not text:
            return False

        speech_text = (
            prepare_text_for_speech(text, max_chars=self.config.max_chars)
            if prepare
            else text
        )
        if not speech_text:
            return False

        try:
            return self.backend.speak(speech_text)
        except Exception as exc:  # noqa: BLE001 — awaaz fail ho to agent na ruke
            log.warning("TTS fail (agent chalta rahega): %s", exc)
            return False

    def save(self, text: str, path: str | Path) -> Path | None:
        """Audio file banao."""
        speech_text = prepare_text_for_speech(text, max_chars=self.config.max_chars)
        if not speech_text:
            return None
        return self.backend.synthesize_to_file(speech_text, path)

    # ------------------------------------------------------------------

    def status(self) -> str:
        """CLI ke liye status."""
        backend = self.backend
        lines = [f"  TTS: {backend.name} ({backend.quality})"]

        if not self.has_voice:
            lines.append("       Awaaz chahiye to inme se koi setup kar:")
            lines.append("         piper  -> best quality")
            lines.append("         espeak -> sudo apt install espeak-ng (halka)")

        return "\n".join(lines)

    @staticmethod
    def available_backends() -> list[tuple[str, bool, str]]:
        """
        Saare backends ki status.

        Returns: [(name, available, quality), ...]
        """
        out: list[tuple[str, bool, str]] = []
        for backend_class in BACKEND_ORDER:
            backend = backend_class()
            try:
                available = backend.is_available()
            except Exception:  # noqa: BLE001
                available = False
            out.append((backend.name, available, backend.quality))
        return out
