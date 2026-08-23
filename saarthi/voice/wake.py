"""
Wake Word — "Hey Saarthi" bolke agent jagana.

TEEN MODES hain, aur DEFAULT jaan-boojh ke sabse simple rakha hai:

    1. PUSH-TO-TALK (default)
       Enter dabao, bolo. Bas.
       Setup: KUCH NAHI. Hamesha chalta hai.
       Sabse reliable — isse shuruat kar.

    2. ENERGY (koi bhi awaaz)
       Zor se bolo, agent jaag jaata hai.
       Setup: kuch nahi (bas mic)
       Problem: TV/gaana/baat-cheet se bhi jaag jaata hai.

    3. PORCUPINE (asli wake word)
       "Jarvis" bolo, agent jaagta hai.
       Setup: free access key chahiye (Picovoice Console se)
       Best experience, par ek step extra.


"HEY SAARTHI" KA SACH:
    Porcupine ke built-in keywords mein "saarthi" nahi hai. Available:
        jarvis, computer, alexa, hey google, hey siri, porcupine,
        bumblebee, terminator, blueberry, grasshopper, ...

    Default humne "jarvis" rakha hai (sabse close feel deta hai).

    Apna "Hey Saarthi" chahiye? Picovoice Console pe FREE custom wake
    word train kar sakta hai:
        https://console.picovoice.ai/
    Wahan se .ppn file milegi, usko PORCUPINE_KEYWORD_PATH mein daal de.


DESIGN NOTE (ek asli technical detail):
    Porcupine EXACTLY 512 samples ka frame maangta hai. Hamara audio
    chunk 480 samples (30ms) ka hai. Mismatch hai!

    Isliye humne frame BUFFER banaya hai — chunks jama karta hai aur
    Porcupine ko theek 512 ke frames deta hai. Ye detail miss karne pe
    Porcupine chup-chaap kaam nahi karta.
"""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .audio import (
    HAS_NUMPY,
    AudioConfig,
    is_audio_available,
    rms,
)

log = logging.getLogger("saarthi.voice.wake")

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import sounddevice as sd

    HAS_SOUNDDEVICE = True
except Exception:  # noqa: BLE001
    sd = None  # type: ignore[assignment]
    HAS_SOUNDDEVICE = False

try:
    import pvporcupine

    HAS_PORCUPINE = True
    PORCUPINE_ERROR = ""
except Exception as exc:  # noqa: BLE001
    pvporcupine = None  # type: ignore[assignment]
    HAS_PORCUPINE = False
    PORCUPINE_ERROR = str(exc)


# ======================================================================
#  Config
# ======================================================================


@dataclass
class WakeConfig:
    """Wake word ki settings."""

    # push_to_talk | energy | porcupine
    mode: str = "push_to_talk"

    # --- Porcupine ---
    access_key: str = ""
    keyword: str = "jarvis"          # built-in keyword
    keyword_path: str = ""           # custom .ppn file
    sensitivity: float = 0.5         # 0-1, zyada = jaldi trigger (aur false alarms)

    # --- Energy mode ---
    energy_threshold: float = 1500.0
    energy_chunks: int = 4           # itne consecutive loud chunks

    @classmethod
    def from_env(cls) -> "WakeConfig":
        def _float(key: str, default: float) -> float:
            raw = os.getenv(key)
            try:
                return float(raw) if raw else default
            except ValueError:
                return default

        return cls(
            mode=os.getenv("WAKE_MODE", "push_to_talk").strip().lower(),
            access_key=os.getenv("PORCUPINE_ACCESS_KEY", "").strip(),
            keyword=os.getenv("PORCUPINE_KEYWORD", "jarvis").strip().lower(),
            keyword_path=os.getenv("PORCUPINE_KEYWORD_PATH", "").strip(),
            sensitivity=_float("PORCUPINE_SENSITIVITY", 0.5),
            energy_threshold=_float("WAKE_ENERGY_THRESHOLD", 1500.0),
            energy_chunks=int(_float("WAKE_ENERGY_CHUNKS", 4)),
        )


# ======================================================================
#  Base
# ======================================================================


class WakeDetector(ABC):
    """Wake detector ka interface."""

    name: str = "unknown"
    description: str = ""

    def __init__(
        self,
        config: WakeConfig | None = None,
        audio_config: AudioConfig | None = None,
    ):
        self.config = config or WakeConfig()
        self.audio_config = audio_config or AudioConfig()

    @abstractmethod
    def is_available(self) -> bool:
        """Ye mode use ho sakta hai?"""
        raise NotImplementedError

    def unavailable_reason(self) -> str:
        """
        Available nahi hai to KYU nahi — ek line mein.

        Ye zaroori hai: user ko pata hona chahiye ki mic ki dikkat hai
        ya key ki. Warna wo galat cheez debug karta rahega.
        """
        if self.is_available():
            return ""
        if not is_audio_available():
            return "mic available nahi hai"
        if not HAS_NUMPY:
            return "numpy install nahi hai"
        return "setup adhoora hai"

    @abstractmethod
    def wait_for_wake(self) -> bool:
        """
        Wake signal ka intezaar karo.

        Returns:
            True  -> jaago, sun lo
            False -> user ne band karne ko bola (Ctrl+C / quit)

        BLOCKING hai — jab tak wake na ho ya user quit na kare.
        """
        raise NotImplementedError

    def setup_help(self) -> str:
        return f"{self.name} available nahi hai."

    def close(self) -> None:
        """Resources free karo."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} available={self.is_available()}>"


# ======================================================================
#  1. Push-to-talk — DEFAULT, hamesha chalta hai
# ======================================================================


class PushToTalkWake(WakeDetector):
    """
    Enter dabao, bolo.

    Ye DEFAULT hai kyunki:
      - Zero setup
      - Zero false alarms
      - Hamesha kaam karta hai
      - Free tier tokens bachte hain (galti se trigger nahi hota)

    Wake word fancy lagta hai, par shuruat ke liye ye behtar hai.
    """

    name = "push_to_talk"
    description = "Enter dabao aur bolo (zero setup)"

    def is_available(self) -> bool:
        return True

    def wait_for_wake(self) -> bool:
        try:
            answer = input("\n  [Enter dabao aur bolo, ya 'q' se band karo] ")
        except (EOFError, KeyboardInterrupt):
            return False

        if answer.strip().lower() in ("q", "quit", "exit", "band", "bye"):
            return False
        return True


# ======================================================================
#  2. Energy — koi bhi awaaz
# ======================================================================


class EnergyWake(WakeDetector):
    """
    Koi bhi tez awaaz se jaag jaata hai.

    Free hai, koi key nahi chahiye. Par TV, gaana, ya doosron ki
    baat-cheet se bhi trigger ho jaata hai. Shaant kamre mein theek hai.
    """

    name = "energy"
    description = "Koi bhi tez awaaz (no setup, par false alarms hote hain)"

    def is_available(self) -> bool:
        return is_audio_available() and HAS_NUMPY

    def wait_for_wake(self) -> bool:
        if not self.is_available():
            log.warning("Energy wake available nahi: %s", self.unavailable_reason())
            return False

        loud_streak = 0

        try:
            stream = sd.InputStream(
                samplerate=self.audio_config.sample_rate,
                channels=self.audio_config.channels,
                dtype="int16",
                blocksize=self.audio_config.chunk_samples,
            )
            with stream:
                while True:
                    chunk, _ = stream.read(self.audio_config.chunk_samples)
                    flat = chunk.ravel() if hasattr(chunk, "ravel") else chunk

                    if rms(flat) > self.config.energy_threshold:
                        loud_streak += 1
                        if loud_streak >= self.config.energy_chunks:
                            return True
                    else:
                        loud_streak = 0

        except KeyboardInterrupt:
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("Energy wake fail: %s", exc)
            return False

    def setup_help(self) -> str:
        return (
            "Energy wake ke liye mic chahiye:\n"
            "    pip install sounddevice numpy\n"
            "    + PortAudio (sudo apt install libportaudio2)"
        )


# ======================================================================
#  3. Porcupine — asli wake word
# ======================================================================


class PorcupineWake(WakeDetector):
    """
    Asli wake word detection — "Jarvis" bolo aur agent jaage.

    Free access key chahiye: https://console.picovoice.ai/
    """

    name = "porcupine"
    description = 'Asli wake word ("jarvis") — free key chahiye'

    def __init__(
        self,
        config: WakeConfig | None = None,
        audio_config: AudioConfig | None = None,
    ):
        super().__init__(config, audio_config)
        self._engine = None
        self._checked = False
        self._error = ""

    # ------------------------------------------------------------------

    def _build(self) -> bool:
        """Porcupine engine banao (lazy)."""
        if self._engine is not None:
            return True
        if self._checked:
            return False

        self._checked = True

        if not HAS_PORCUPINE:
            self._error = f"pvporcupine install nahi hai ({PORCUPINE_ERROR})"
            return False

        if not self.config.access_key:
            self._error = "PORCUPINE_ACCESS_KEY nahi mila"
            return False

        kwargs: dict = {
            "access_key": self.config.access_key,
            "sensitivities": [self.config.sensitivity],
        }

        # Custom .ppn file (apna "Hey Saarthi") ya built-in keyword
        if self.config.keyword_path:
            kwargs["keyword_paths"] = [self.config.keyword_path]
        else:
            available = set(getattr(pvporcupine, "KEYWORDS", set()))
            keyword = self.config.keyword
            if available and keyword not in available:
                self._error = (
                    f"'{keyword}' built-in keyword nahi hai.\n"
                    f"  Available: {', '.join(sorted(available))}"
                )
                return False
            kwargs["keywords"] = [keyword]

        try:
            self._engine = pvporcupine.create(**kwargs)
            log.info(
                "Porcupine ready (keyword=%s, frame_length=%d, sample_rate=%d)",
                self.config.keyword_path or self.config.keyword,
                self._engine.frame_length,
                self._engine.sample_rate,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._error = f"Porcupine banane mein problem: {exc}"
            return False

    def is_available(self) -> bool:
        # _build() PEHLE call karte hain, short-circuit se pehle.
        #
        # Kyun: agar mic na ho aur hum `is_audio_available() and _build()`
        # likhte, to _build() kabhi nahi chalta aur self._error khali
        # reh jaata — user ko pata hi nahi chalta ki key missing hai.
        # Dono problems ek saath report karni chahiye.
        engine_ok = self._build()
        return engine_ok and is_audio_available() and HAS_NUMPY

    def unavailable_reason(self) -> str:
        if self.is_available():
            return ""

        problems: list[str] = []
        if self._error:
            problems.append(self._error.splitlines()[0])
        if not is_audio_available():
            problems.append("mic available nahi hai")
        if not HAS_NUMPY:
            problems.append("numpy install nahi hai")

        return "; ".join(problems) or "setup adhoora hai"

    # ------------------------------------------------------------------

    def wait_for_wake(self) -> bool:
        if not self.is_available():
            log.warning("Porcupine available nahi hai")
            return False

        engine = self._engine
        frame_length = engine.frame_length      # usually 512
        sample_rate = engine.sample_rate        # usually 16000

        # --- FRAME BUFFER ---
        # Porcupine ko THEEK frame_length samples chahiye. Hamare chunks
        # alag size ke hote hain (480). Isliye buffer karke exact frames
        # banate hain. Ye detail miss karne pe Porcupine silently
        # kaam nahi karta.
        buffer: list = []
        buffered = 0

        try:
            stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                blocksize=frame_length,
            )
            with stream:
                while True:
                    chunk, _ = stream.read(frame_length)
                    flat = chunk.ravel() if hasattr(chunk, "ravel") else chunk

                    buffer.append(flat)
                    buffered += len(flat)

                    # Poore frames nikaalo
                    while buffered >= frame_length:
                        combined = (
                            np.concatenate(buffer) if len(buffer) > 1 else buffer[0]
                        )
                        frame = combined[:frame_length]
                        leftover = combined[frame_length:]

                        buffer = [leftover] if len(leftover) else []
                        buffered = len(leftover)

                        if engine.process(frame.tolist()) >= 0:
                            log.info("Wake word suna!")
                            return True

        except KeyboardInterrupt:
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("Porcupine listening fail: %s", exc)
            return False

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.delete()
            except Exception:  # noqa: BLE001
                pass
            self._engine = None

    def setup_help(self) -> str:
        lines = ["Porcupine wake word setup:"]
        lines.append("")
        lines.append("  1. pip install pvporcupine")
        lines.append("")
        lines.append("  2. FREE access key le:")
        lines.append("       https://console.picovoice.ai/")
        lines.append("     .env mein daal:")
        lines.append("       PORCUPINE_ACCESS_KEY=tera_key")
        lines.append("       WAKE_MODE=porcupine")
        lines.append("")
        lines.append("  3. Keyword chuno (built-in, free):")
        available = sorted(getattr(pvporcupine, "KEYWORDS", []) or [])
        if available:
            lines.append(f"       {', '.join(available)}")
        lines.append("     .env mein: PORCUPINE_KEYWORD=jarvis")
        lines.append("")
        lines.append('  Apna "Hey Saarthi" chahiye?')
        lines.append("     Picovoice Console pe free custom wake word train kar,")
        lines.append("     .ppn file download kar, phir:")
        lines.append("       PORCUPINE_KEYWORD_PATH=/path/to/hey_saarthi.ppn")
        if self._error:
            lines.append("")
            lines.append(f"  Abhi ka error: {self._error}")
        return "\n".join(lines)


# ======================================================================
#  Factory
# ======================================================================

WAKE_MODES: dict[str, type[WakeDetector]] = {
    "push_to_talk": PushToTalkWake,
    "ptt": PushToTalkWake,
    "enter": PushToTalkWake,
    "energy": EnergyWake,
    "porcupine": PorcupineWake,
    "wake_word": PorcupineWake,
}


def create_wake_detector(
    config: WakeConfig | None = None,
    audio_config: AudioConfig | None = None,
) -> WakeDetector:
    """
    Config ke hisaab se wake detector banao.

    Maanga hua mode na chale to PUSH-TO-TALK pe fallback karta hai —
    kyunki wo hamesha chalta hai. Agent kabhi nahi rukta.
    """
    config = config or WakeConfig()
    audio_config = audio_config or AudioConfig()

    mode = (config.mode or "push_to_talk").lower()
    detector_class = WAKE_MODES.get(mode)

    if detector_class is None:
        log.warning(
            "WAKE_MODE '%s' unknown hai. Available: %s. Push-to-talk use kar raha hun.",
            mode,
            ", ".join(sorted(set(WAKE_MODES))),
        )
        return PushToTalkWake(config, audio_config)

    detector = detector_class(config, audio_config)

    if detector.is_available():
        return detector

    log.warning(
        "Wake mode '%s' available nahi hai, push-to-talk use kar raha hun.\n%s",
        mode,
        detector.setup_help(),
    )
    return PushToTalkWake(config, audio_config)


def available_wake_modes() -> list[tuple[str, bool, str]]:
    """
    Kaunse wake modes available hain.

    Returns: [(name, available, description), ...]
    """
    out: list[tuple[str, bool, str]] = []
    seen: set[str] = set()

    for detector_class in (PushToTalkWake, EnergyWake, PorcupineWake):
        if detector_class.name in seen:
            continue
        seen.add(detector_class.name)

        detector = detector_class()
        try:
            available = detector.is_available()
        except Exception:  # noqa: BLE001
            available = False
        out.append((detector.name, available, detector.description))
        detector.close()

    return out
