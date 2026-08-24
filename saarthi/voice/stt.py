"""
Speech-to-Text — faster-whisper se, Hinglish tuning ke saath.

Ye layer teen kaam karti hai:
    1. Whisper model load karna (offline, free, tera laptop pe)
    2. Hinglish BIASING lagana (initial_prompt)
    3. Output ko CORRECT karna (hinglish_asr.py se)

    Mic audio -> [Whisper + biasing] -> raw text -> [correction] -> clean text


EK ZAROORI DESIGN DECISION — language setting:

    Whisper ko language batana padta hai. Hinglish ke liye do options:

    language="hi"  -> Devanagari mein output deta hai
                      "पेटीएम खोलो"
                      Phir humein transliterate karna padta hai.

    language="en"  -> Roman script mein output deta hai
                      "paytm kholo"
                      Hindi words thode galat sun sakta hai, par
                      script humein chahiye wahi hai.

    HUM DEFAULT "en" RAKHTE HAIN. Kyun?
      - Hamara pura lexicon (110 apps, intents) ROMAN mein hai
      - App naam Latin script mein hi hote hain (Paytm, IRCTC)
      - Hindi words ki galtiyan hamari correction layer pakad leti hai
      - Devanagari aa bhi jaaye to transliterate() handle kar leta hai

    Dono try kar ke dekh — .env mein WHISPER_LANGUAGE badal ke.


MODEL SIZE (PILLAR #3 — budget hardware):

    Model    RAM      Speed      Accuracy    Kiske liye
    ------   ------   --------   ---------   ---------------------------
    tiny     ~1 GB    bahut tez  kaam chal   testing, purana laptop
    base     ~1 GB    tez        theek       4GB RAM wala laptop  <- default
    small    ~2 GB    medium     acchi       8GB RAM, recommended
    medium   ~5 GB    dheemi     bahut acchi 16GB RAM
    large-v3 ~10 GB   bahut dheemi best      GPU chahiye

    Sab FREE hain. Pehli baar download hota hai, phir offline chalta hai.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .hinglish_asr import (
    CorrectionResult,
    build_initial_prompt,
    correct_transcript,
    looks_like_garbage,
)

log = logging.getLogger("saarthi.voice.stt")

# ----------------------------------------------------------------------
#  Optional dependencies
# ----------------------------------------------------------------------

try:
    from faster_whisper import WhisperModel

    HAS_WHISPER = True
    WHISPER_ERROR = ""
except Exception as exc:  # noqa: BLE001
    WhisperModel = None  # type: ignore[assignment,misc]
    HAS_WHISPER = False
    WHISPER_ERROR = str(exc)

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False


# ----------------------------------------------------------------------
#  Config
# ----------------------------------------------------------------------

MODEL_INFO: dict[str, str] = {
    "tiny": "~1GB RAM, bahut tez, accuracy kaam chalau",
    "base": "~1GB RAM, tez, accuracy theek — 4GB laptop ke liye",
    "small": "~2GB RAM, medium speed, acchi accuracy — recommended",
    "medium": "~5GB RAM, dheemi, bahut acchi accuracy",
    "large-v3": "~10GB RAM, GPU chahiye, best accuracy",
}


@dataclass
class WhisperConfig:
    """Whisper ki settings."""

    # Model size — chhota = tez + kam RAM
    model_size: str = "base"

    # cpu | cuda | auto
    device: str = "cpu"

    # int8 = kam RAM, float16 = GPU pe fast
    compute_type: str = "int8"

    # "en" ya "hi" ya None (auto-detect). Upar wali baat padh.
    language: str | None = "en"

    # Zyada beam = better accuracy, par dheemi
    beam_size: int = 5

    # Whisper ka andar ka silence filter — hallucination kam karta hai
    vad_filter: bool = True

    # Model kahan cache ho (None = default HuggingFace cache)
    download_root: str | None = None

    # Kitne CPU threads
    cpu_threads: int = 0  # 0 = auto

    @classmethod
    def from_env(cls) -> "WhisperConfig":
        """.env se settings padho."""

        def _int(key: str, default: int) -> int:
            raw = os.getenv(key)
            try:
                return int(raw) if raw else default
            except ValueError:
                return default

        def _bool(key: str, default: bool) -> bool:
            raw = os.getenv(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "haan", "y"}

        language = os.getenv("WHISPER_LANGUAGE", "en").strip()

        return cls(
            model_size=os.getenv("WHISPER_MODEL", "base").strip(),
            device=os.getenv("WHISPER_DEVICE", "cpu").strip(),
            compute_type=os.getenv("WHISPER_COMPUTE", "int8").strip(),
            language=None if language.lower() in ("auto", "", "none") else language,
            beam_size=_int("WHISPER_BEAM_SIZE", 5),
            vad_filter=_bool("WHISPER_VAD", True),
            download_root=os.getenv("WHISPER_CACHE") or None,
            cpu_threads=_int("WHISPER_THREADS", 0),
        )

    def describe(self) -> str:
        info = MODEL_INFO.get(self.model_size, "")
        lang = self.language or "auto-detect"
        return (
            f"whisper {self.model_size} ({self.device}/{self.compute_type}), "
            f"language={lang}"
            + (f"\n    {info}" if info else "")
        )


# ----------------------------------------------------------------------
#  Result
# ----------------------------------------------------------------------


@dataclass
class TranscriptResult:
    """Ek transcription ka pura result."""

    # Final text — correction ke baad. Agent ko YEHI jaata hai.
    text: str

    # Whisper ne asal mein kya diya (debugging ke liye)
    raw_text: str = ""

    # Correction ka detail
    correction: CorrectionResult | None = None

    # Quality signals
    language: str = ""
    language_probability: float = 0.0
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0

    # Timing
    audio_duration: float = 0.0
    processing_time: float = 0.0

    # Kuch samajh aaya ya nahi
    is_usable: bool = True
    reject_reason: str = ""

    segments: list[str] = field(default_factory=list)

    @property
    def speed_ratio(self) -> float:
        """Audio se kitna tez process hua (>1 = realtime se tez)."""
        if self.processing_time <= 0:
            return 0.0
        return self.audio_duration / self.processing_time

    def explain(self) -> str:
        """Debug output."""
        lines = [f'Text: "{self.text}"']

        if self.raw_text and self.raw_text != self.text:
            lines.append(f'Whisper ne suna: "{self.raw_text}"')

        if self.correction and self.correction.changes:
            lines.append("Corrections:")
            for before, after in self.correction.changes:
                lines.append(f"  '{before}' -> '{after}'")

        lines.append(
            f"Quality: lang={self.language} ({self.language_probability:.2f}), "
            f"logprob={self.avg_logprob:.2f}, no_speech={self.no_speech_prob:.2f}"
        )
        lines.append(
            f"Speed: {self.audio_duration:.1f}s audio in "
            f"{self.processing_time:.1f}s ({self.speed_ratio:.1f}x realtime)"
        )

        if not self.is_usable:
            lines.append(f"REJECTED: {self.reject_reason}")

        return "\n".join(lines)


# `transcribe(language=...)` ke liye sentinel.
#
# `None` ka apna matlab hai (auto-detect), isliye "user ne kuch diya
# hi nahi" ke liye alag object chahiye.
_USE_CONFIG = object()


class STTError(Exception):
    """STT layer ki problem."""


# ----------------------------------------------------------------------
#  Availability
# ----------------------------------------------------------------------


def is_stt_available() -> bool:
    """Speech-to-text kar sakte hain?"""
    return HAS_WHISPER


def stt_setup_help() -> str:
    """Whisper na ho to kya karna hai."""
    lines = ["Speech-to-text available nahi hai."]
    lines.append("")
    lines.append("  Install kar (free hai):")
    lines.append("      pip install faster-whisper")
    if WHISPER_ERROR:
        lines.append(f"    (error: {WHISPER_ERROR})")
    lines.append("")
    lines.append("  Pehli baar model download hoga (~150MB base ke liye).")
    lines.append("  Uske baad offline chalega — internet ki zarurat nahi.")
    return "\n".join(lines)


def total_ram_gb() -> float:
    """
    Machine ki total RAM (GB mein). Pata na chale to 0.0.

    ⚠️ YE FUNCTION EK ASLI BUG SE BANA HAI.

    Pehle sirf do tareeke the — `/proc/meminfo` aur `os.sysconf()`.
    DONO UNIX-ONLY HAIN. Windows pe `/proc` nahi hota aur `os.sysconf`
    exist hi nahi karta (AttributeError). Nateeja: Windows pe ye
    HAMESHA 0 return karta tha aur model "base" pe atak jaata tha —
    chahe machine mein 32GB RAM ho.

    Aur "base" Hinglish pe kamzor hai. User ne "paytm kholo" bola aur
    Whisper ne "Kya kya ouri website, proper da yaar uca" suna. Wajah
    yahi thi: budget-hardware wala fallback bade laptop pe bhi lag
    raha tha.
    """
    # --- Windows ---
    if sys.platform.startswith("win"):
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / (1024**3)
        except Exception:  # noqa: BLE001
            pass

    # --- Linux ---
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except Exception:  # noqa: BLE001
        pass

    # --- macOS / BSD ---
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                return int(out) / (1024**3)
        except Exception:  # noqa: BLE001
            pass

    # --- Unix fallback ---
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024**3)
    except (ValueError, OSError, AttributeError):
        pass

    # --- psutil ho to (dependency nahi hai, par ho sakta hai) ---
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except Exception:  # noqa: BLE001
        return 0.0


def recommend_model_size() -> str:
    """
    Available RAM ke hisaab se model suggest karo.

    Pillar #3 — budget hardware pe bhi chale. PAR bade laptop pe
    kamzor model thopna bhi galat hai, kyunki `base` Hinglish pe
    theek se kaam nahi karta.
    """
    total_gb = total_ram_gb()

    if total_gb <= 0:
        return "base"  # Pata nahi chala — safe default
    if total_gb < 3:
        return "tiny"
    if total_gb < 6:
        return "base"
    if total_gb < 12:
        return "small"
    return "medium"


# ----------------------------------------------------------------------
#  STT engine
# ----------------------------------------------------------------------


class WhisperSTT:
    """
    Whisper-based speech-to-text, Hinglish tuning ke saath.

    Model LAZY load hota hai — pehli transcribe pe. Isliye object
    banane se kuch download nahi hota.

    Use:
        stt = WhisperSTT()
        result = stt.transcribe(audio, extra_words=["mummy", "bijli ka bill"])
        print(result.text)
    """

    # Ye quality thresholds hallucination reject karne ke liye hain
    MIN_LOGPROB = -1.0        # Isse neeche = model confident nahi
    MAX_NO_SPEECH_PROB = 0.6  # Isse upar = shayad koi bola hi nahi

    def __init__(self, config: WhisperConfig | None = None):
        self.config = config or WhisperConfig()
        self._model = None
        self._load_time = 0.0

    # ------------------------------------------------------------------
    #  Model loading
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """
        Model load karo. Pehli baar download hoga.

        Idempotent — dobara call karne se kuch nahi hota.
        """
        if self._model is not None:
            return

        if not HAS_WHISPER:
            raise STTError(stt_setup_help())

        started = time.time()
        log.info(
            "Whisper model load ho raha hai: %s (pehli baar download hoga)",
            self.config.model_size,
        )

        kwargs: dict = {
            "device": self.config.device,
            "compute_type": self.config.compute_type,
        }
        if self.config.download_root:
            kwargs["download_root"] = self.config.download_root
        if self.config.cpu_threads > 0:
            kwargs["cpu_threads"] = self.config.cpu_threads

        try:
            self._model = WhisperModel(self.config.model_size, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise STTError(
                f"Whisper model load nahi hua ({self.config.model_size}): {exc}\n"
                f"Chhota model try kar — .env mein WHISPER_MODEL=tiny"
            ) from exc

        self._load_time = time.time() - started
        log.info("Model load ho gaya (%.1fs)", self._load_time)

    def unload(self) -> None:
        """Model memory se hatao (RAM bachane ke liye)."""
        self._model = None

    # ------------------------------------------------------------------
    #  Audio prep
    # ------------------------------------------------------------------

    def _prepare_audio(self, audio):
        """
        Audio ko Whisper ke format mein laao.

        Whisper float32 [-1, 1] maangta hai. Hamara recorder int16
        deta hai (0-32767). Isliye convert karna padta hai —
        warna Whisper ko sirf shor sunai dega.
        """
        # File path
        if isinstance(audio, (str, Path)):
            return str(audio)

        if not HAS_NUMPY:
            raise STTError("numpy chahiye audio array ke liye: pip install numpy")

        array = np.asarray(audio)

        # int16 -> float32 normalize
        if array.dtype == np.int16:
            return array.astype(np.float32) / 32768.0

        if array.dtype in (np.float32, np.float64):
            result = array.astype(np.float32)
            # Agar range [-1,1] se bahar hai to normalize kar do
            peak = float(np.abs(result).max()) if result.size else 0.0
            if peak > 1.5:
                result = result / 32768.0
            return result

        return array.astype(np.float32)

    # ------------------------------------------------------------------
    #  Transcription
    # ------------------------------------------------------------------

    def transcribe(
        self,
        audio,
        extra_words: list[str] | None = None,
        apply_correction: bool = True,
        language=_USE_CONFIG,
    ) -> TranscriptResult:
        """
        Audio ko text banao.

        Args:
            audio: numpy array (int16 ya float32) ya WAV file path
            extra_words: Extra vocabulary — contact naam, skill naam.
                         Ye Whisper ko bias karta hai (PILLAR #1)
            apply_correction: Hinglish correction lagani hai?
            language: Is call ke liye language override ("en"/"hi"/None).
                      Na do to config ka use hota hai.

        Returns:
            TranscriptResult — .text mein final saaf text
        """
        self.load()

        started = time.time()
        prepared = self._prepare_audio(audio)

        # --- PILLAR #1: Hinglish biasing ---
        initial_prompt = build_initial_prompt(extra_words=extra_words)

        try:
            # `language` override diya ho to wo use karo, warna config ka.
            # Ye --stt-tune ke liye chahiye: ek hi model load karke
            # en / hi / auto teeno try kar sakein.
            use_language = (
                self.config.language if language is _USE_CONFIG else language
            )

            segments_iter, info = self._model.transcribe(
                prepared,
                language=use_language,
                initial_prompt=initial_prompt,
                beam_size=self.config.beam_size,
                vad_filter=self.config.vad_filter,
                condition_on_previous_text=False,  # hallucination kam karta hai
            )
        except Exception as exc:  # noqa: BLE001
            raise STTError(f"Transcription fail hua: {exc}") from exc

        # segments ek generator hai — iterate karna padta hai
        segment_texts: list[str] = []
        logprobs: list[float] = []
        no_speech_probs: list[float] = []

        for segment in segments_iter:
            text = (segment.text or "").strip()
            if text:
                segment_texts.append(text)
            if getattr(segment, "avg_logprob", None) is not None:
                logprobs.append(segment.avg_logprob)
            if getattr(segment, "no_speech_prob", None) is not None:
                no_speech_probs.append(segment.no_speech_prob)

        raw_text = " ".join(segment_texts).strip()
        processing_time = time.time() - started

        avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0.0
        no_speech = (
            sum(no_speech_probs) / len(no_speech_probs) if no_speech_probs else 0.0
        )

        result = TranscriptResult(
            text=raw_text,
            raw_text=raw_text,
            language=getattr(info, "language", "") or "",
            language_probability=getattr(info, "language_probability", 0.0) or 0.0,
            avg_logprob=avg_logprob,
            no_speech_prob=no_speech,
            audio_duration=getattr(info, "duration", 0.0) or 0.0,
            processing_time=processing_time,
            segments=segment_texts,
        )

        # --- Quality checks ---
        if not raw_text:
            result.is_usable = False
            result.reject_reason = "kuch sunai nahi diya"
            return result

        if looks_like_garbage(raw_text):
            result.is_usable = False
            result.reject_reason = f"bakwas output ('{raw_text}') — shayad shor tha"
            return result

        if no_speech > self.MAX_NO_SPEECH_PROB:
            result.is_usable = False
            result.reject_reason = (
                f"no_speech_prob {no_speech:.2f} bahut zyada — koi bola nahi lagta"
            )
            return result

        if logprobs and avg_logprob < self.MIN_LOGPROB:
            result.is_usable = False
            result.reject_reason = (
                f"confidence kam hai (logprob {avg_logprob:.2f}) — dobara bol"
            )
            return result

        # --- PILLAR #1: Hinglish correction ---
        if apply_correction:
            correction = correct_transcript(raw_text)
            result.correction = correction
            result.text = correction.corrected

            # Correction ke baad bhi bakwas hai to reject
            if looks_like_garbage(result.text):
                result.is_usable = False
                result.reject_reason = "correction ke baad bhi kuch samajh nahi aaya"

        return result

    def transcribe_file(
        self, path: str | Path, extra_words: list[str] | None = None
    ) -> TranscriptResult:
        """WAV/MP3 file se transcribe karo."""
        file_path = Path(path)
        if not file_path.exists():
            raise STTError(f"Audio file nahi mili: {path}")
        return self.transcribe(str(file_path), extra_words=extra_words)

    def status(self) -> str:
        """CLI ke liye status."""
        if not HAS_WHISPER:
            return "  STT: available nahi (pip install faster-whisper)"

        loaded = (
            f"loaded ({self._load_time:.1f}s)" if self.is_loaded else "load nahi hua"
        )
        return f"  STT: {self.config.describe()}\n       {loaded}"
