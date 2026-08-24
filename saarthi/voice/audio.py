"""
Audio I/O — mic se sunna, speaker pe bolna.

DESIGN DECISION (ye important hai):
    Silence detection ka LOGIC hardware se alag rakha hai.

    `SilenceDetector` ek pure state machine hai — usko audio chunks do,
    wo batayega ki bolna shuru hua ya khatam. Isme koi microphone nahi
    hai. Isliye:
      - Sandbox/CI mein test ho sakta hai (bina mic ke)
      - Tuning aasaan hai
      - Bug dhoondhna aasaan hai

    `Recorder` sirf mic se chunks laata hai aur detector se puchta hai.

DEPENDENCIES (sab optional):
    sounddevice  -> mic + speaker    (pip install sounddevice)
    numpy        -> audio math       (faster-whisper ke saath aata hai)

Inke bina bhi ye module import ho jaayega — bas `is_audio_available()`
False batayega aur clear error milega. Crash nahi hoga.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger("saarthi.voice.audio")

# ----------------------------------------------------------------------
#  Optional dependencies
# ----------------------------------------------------------------------

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

try:
    import sounddevice as sd

    HAS_SOUNDDEVICE = True
    SOUNDDEVICE_ERROR = ""
except Exception as exc:  # noqa: BLE001 — PortAudio missing bhi OSError deta hai
    sd = None  # type: ignore[assignment]
    HAS_SOUNDDEVICE = False
    SOUNDDEVICE_ERROR = str(exc)


# ----------------------------------------------------------------------
#  Config
# ----------------------------------------------------------------------

# Whisper 16kHz mono expect karta hai — isliye yahi default
SAMPLE_RATE = 16_000
CHANNELS = 1
CHUNK_MS = 30  # Har chunk kitne ms ka (30ms = VAD ke liye standard)


@dataclass
class AudioConfig:
    """Recording ki settings."""

    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS
    chunk_ms: int = CHUNK_MS

    # Kaunsa microphone use karna hai.
    #
    # None = system ka default. PAR YE ASLI PROBLEM HAI:
    # Windows pe default aksar "Microsoft Sound Mapper - Input" hota hai,
    # jo ek legacy MME wrapper hai. Usse recording aati hai par BAHUT
    # DHEEMI (peak ~300 out of 32767 = practically silence). Whisper ko
    # phir kuch sunai nahi deta aur user ko lagta hai voice tuta hua hai.
    #
    # Ye asli bug hai jo user ki machine pe mila. Fix: .env mein
    # SAARTHI_MIC_DEVICE se asli mic chun lo.
    # Kaunsa chunna hai wo pata karne ke liye: python hardware_check.py --mic-scan
    device: int | None = None

    # --- Silence detection tuning ---

    # Background noise se kitna zyada loud ho tab "bolna" maana jaaye
    noise_multiplier: float = 2.5

    # Minimum threshold — bilkul silent room mein bhi itna chahiye
    # (int16 scale pe, 0-32767)
    min_threshold: float = 300.0

    # Bolna shuru hua maanne ke liye kitne consecutive loud chunks
    speech_start_chunks: int = 3

    # Bolna khatam — kitni der ka silence
    silence_duration: float = 1.0

    # Zyada se zyada kitna record karna hai (safety)
    max_duration: float = 30.0

    # Bolna shuru hi na ho to kitni der wait karein
    start_timeout: float = 10.0

    # Noise floor calibrate karne ka time
    calibration_duration: float = 0.5

    @property
    def chunk_samples(self) -> int:
        """Ek chunk mein kitne samples."""
        return int(self.sample_rate * self.chunk_ms / 1000)

    @property
    def chunks_per_second(self) -> float:
        return 1000.0 / self.chunk_ms

    @property
    def silence_chunks(self) -> int:
        """Kitne silent chunks ke baad rukna hai."""
        return max(1, int(self.silence_duration * self.chunks_per_second))

    @property
    def max_chunks(self) -> int:
        return int(self.max_duration * self.chunks_per_second)

    @property
    def start_timeout_chunks(self) -> int:
        return int(self.start_timeout * self.chunks_per_second)

    @property
    def calibration_chunks(self) -> int:
        return max(1, int(self.calibration_duration * self.chunks_per_second))

    @classmethod
    def from_env(cls) -> "AudioConfig":
        """
        .env se settings padho.

        Baaki configs (WhisperConfig, TTSConfig) ki tarah ye bhi ab
        env-aware hai. Pehle nahi thi, isliye SAARTHI_MIC_DEVICE jaisi
        setting ka koi tareeka hi nahi tha.
        """
        import os

        config = cls()

        raw_device = os.getenv("SAARTHI_MIC_DEVICE", "").strip()
        if raw_device:
            config.device = resolve_device(raw_device)

        raw_min = os.getenv("SAARTHI_MIC_MIN_THRESHOLD", "").strip()
        if raw_min:
            try:
                config.min_threshold = float(raw_min)
            except ValueError:
                pass

        return config


# ----------------------------------------------------------------------
#  RMS — audio kitna loud hai
# ----------------------------------------------------------------------


def rms(chunk) -> float:
    """
    Audio chunk ka loudness (Root Mean Square).

    numpy ho to fast, warna pure Python fallback.
    int16 audio expect karta hai (0-32767 scale).
    """
    if chunk is None:
        return 0.0

    if HAS_NUMPY and hasattr(chunk, "astype"):
        if chunk.size == 0:
            return 0.0
        # float64 mein convert karo — warna int16 overflow ho jaata hai
        samples = chunk.astype("float64").ravel()
        return float(np.sqrt(np.mean(samples * samples)))

    # Pure Python fallback
    values = list(chunk)
    if not values:
        return 0.0
    total = sum(float(v) * float(v) for v in values)
    return (total / len(values)) ** 0.5


# ----------------------------------------------------------------------
#  Silence detection — pure state machine (testable!)
# ----------------------------------------------------------------------


class ListenState(str, Enum):
    """Detector kis state mein hai."""

    CALIBRATING = "calibrating"    # Background noise naap raha hai
    WAITING = "waiting"            # Bolne ka intezaar
    SPEAKING = "speaking"          # Bolna chal raha hai
    DONE = "done"                  # Bol ke chup ho gaya
    TIMEOUT = "timeout"            # Koi bola hi nahi
    TOO_LONG = "too_long"          # max_duration cross


@dataclass
class DetectorStatus:
    """Ek chunk process karne ka result."""

    state: ListenState
    should_stop: bool = False
    loudness: float = 0.0
    threshold: float = 0.0

    @property
    def is_finished(self) -> bool:
        return self.state in (
            ListenState.DONE,
            ListenState.TIMEOUT,
            ListenState.TOO_LONG,
        )

    @property
    def got_speech(self) -> bool:
        """Kuch bola gaya tha?"""
        return self.state in (ListenState.DONE, ListenState.TOO_LONG)


class SilenceDetector:
    """
    Batata hai ki banda bolna shuru kiya aur kab chup hua.

    Ye PURE LOGIC hai — koi microphone nahi. Chunks feed karo,
    ye state batata hai. Isliye test karna aasaan hai.

    Use:
        detector = SilenceDetector(config)
        for chunk in mic_stream:
            status = detector.feed(chunk)
            if status.is_finished:
                break
    """

    def __init__(self, config: AudioConfig | None = None):
        self.config = config or AudioConfig()
        self.reset()

    def reset(self) -> None:
        """Naya recording shuru karne ke liye."""
        self.state = ListenState.CALIBRATING
        self.noise_floor = 0.0
        self.threshold = self.config.min_threshold

        self._calibration_samples: list[float] = []
        self._loud_streak = 0
        self._silent_streak = 0
        self._chunks_seen = 0
        self._speech_chunks = 0

    # ------------------------------------------------------------------

    def _finish_calibration(self) -> None:
        """Noise floor se threshold set karo."""
        if self._calibration_samples:
            # Median use karte hain, average nahi — ek achanak
            # aawaz (darwaza band hona) calibration kharab na kare
            ordered = sorted(self._calibration_samples)
            self.noise_floor = ordered[len(ordered) // 2]
        else:
            self.noise_floor = 0.0

        self.threshold = max(
            self.noise_floor * self.config.noise_multiplier,
            self.config.min_threshold,
        )
        self.state = ListenState.WAITING

        log.debug(
            "Calibration done: noise_floor=%.1f threshold=%.1f",
            self.noise_floor,
            self.threshold,
        )

    def feed(self, chunk) -> DetectorStatus:
        """
        Ek audio chunk process karo.

        Returns: current status
        """
        loudness = rms(chunk)
        self._chunks_seen += 1

        # --- Calibration phase ---
        if self.state == ListenState.CALIBRATING:
            self._calibration_samples.append(loudness)
            if len(self._calibration_samples) >= self.config.calibration_chunks:
                self._finish_calibration()
            return DetectorStatus(
                state=self.state, loudness=loudness, threshold=self.threshold
            )

        is_loud = loudness > self.threshold

        # --- Bolne ka intezaar ---
        if self.state == ListenState.WAITING:
            if is_loud:
                self._loud_streak += 1
                if self._loud_streak >= self.config.speech_start_chunks:
                    self.state = ListenState.SPEAKING
                    self._silent_streak = 0
                    log.debug("Bolna shuru (loudness=%.1f)", loudness)
            else:
                # Streak toot gaya — ek do loud chunk noise ho sakta hai
                self._loud_streak = 0

            # Bahut der ho gayi, koi bola nahi
            if self._chunks_seen >= self.config.start_timeout_chunks:
                self.state = ListenState.TIMEOUT
                return DetectorStatus(
                    state=self.state,
                    should_stop=True,
                    loudness=loudness,
                    threshold=self.threshold,
                )

            return DetectorStatus(
                state=self.state, loudness=loudness, threshold=self.threshold
            )

        # --- Bolna chal raha hai ---
        if self.state == ListenState.SPEAKING:
            self._speech_chunks += 1

            if is_loud:
                self._silent_streak = 0
            else:
                self._silent_streak += 1
                if self._silent_streak >= self.config.silence_chunks:
                    self.state = ListenState.DONE
                    log.debug("Bolna khatam (%d chunks)", self._speech_chunks)
                    return DetectorStatus(
                        state=self.state,
                        should_stop=True,
                        loudness=loudness,
                        threshold=self.threshold,
                    )

            # Bahut lamba bol raha hai — rok do
            if self._speech_chunks >= self.config.max_chunks:
                self.state = ListenState.TOO_LONG
                return DetectorStatus(
                    state=self.state,
                    should_stop=True,
                    loudness=loudness,
                    threshold=self.threshold,
                )

            return DetectorStatus(
                state=self.state, loudness=loudness, threshold=self.threshold
            )

        # Already finished
        return DetectorStatus(
            state=self.state,
            should_stop=True,
            loudness=loudness,
            threshold=self.threshold,
        )


# ----------------------------------------------------------------------
#  WAV file handling (stdlib se — koi extra dependency nahi)
# ----------------------------------------------------------------------


def save_wav(path: str | Path, audio, sample_rate: int = SAMPLE_RATE) -> Path:
    """
    int16 audio ko WAV file mein save karo.

    `wave` module stdlib mein hai — kuch install nahi karna.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if HAS_NUMPY and hasattr(audio, "tobytes"):
        raw = audio.astype("int16").tobytes()
    elif isinstance(audio, (bytes, bytearray)):
        raw = bytes(audio)
    else:
        import array

        raw = array.array("h", [int(v) for v in audio]).tobytes()

    with wave.open(str(file_path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)  # int16 = 2 bytes
        wav.setframerate(sample_rate)
        wav.writeframes(raw)

    return file_path


def load_wav(path: str | Path) -> tuple[object, int]:
    """
    WAV file padho.

    Returns: (audio, sample_rate) — numpy array ya bytes
    """
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())

    if HAS_NUMPY:
        return np.frombuffer(raw, dtype="int16"), sample_rate
    return raw, sample_rate


# ----------------------------------------------------------------------
#  Availability
# ----------------------------------------------------------------------


def is_audio_available() -> bool:
    """Mic/speaker use kar sakte hain?"""
    if not HAS_SOUNDDEVICE:
        return False
    try:
        sd.query_devices()
        return True
    except Exception:  # noqa: BLE001
        return False


def audio_setup_help() -> str:
    """Audio na chale to user ko kya karna chahiye."""
    lines = ["Audio available nahi hai."]

    if not HAS_SOUNDDEVICE:
        lines.append("")
        lines.append("  1. Python package install kar:")
        lines.append("       pip install sounddevice")
        if SOUNDDEVICE_ERROR:
            lines.append(f"     (error: {SOUNDDEVICE_ERROR})")
        lines.append("")
        lines.append("  2. System library bhi chahiye (PortAudio):")
        lines.append("       Ubuntu/Debian : sudo apt install libportaudio2")
        lines.append("       Fedora        : sudo dnf install portaudio")
        lines.append("       macOS         : brew install portaudio")
        lines.append("       Windows       : already included")
    else:
        lines.append("  Koi audio device nahi mila. Mic laga hai? Check kar.")

    if not HAS_NUMPY:
        lines.append("")
        lines.append("  numpy bhi chahiye: pip install numpy")

    return "\n".join(lines)


def input_devices() -> list[dict]:
    """
    Saare input devices — structured.

    Returns list of:
        {"index": 5, "name": "Microphone Array (Realtek...)",
         "channels": 2, "api": "Windows WASAPI", "is_default": False}

    `list_input_devices()` isi ka string version hai (purana API,
    backward compatibility ke liye rakha hai).
    """
    if not HAS_SOUNDDEVICE:
        return []

    try:
        devices = sd.query_devices()
    except Exception:  # noqa: BLE001
        return []

    try:
        default_index = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_index = None

    try:
        apis = sd.query_hostapis()
    except Exception:  # noqa: BLE001
        apis = []

    out: list[dict] = []
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) <= 0:
            continue

        api_index = device.get("hostapi")
        api_name = ""
        if isinstance(api_index, int) and 0 <= api_index < len(apis):
            api_name = apis[api_index].get("name", "")

        out.append(
            {
                "index": index,
                "name": device.get("name", "?"),
                "channels": device.get("max_input_channels", 0),
                "api": api_name,
                "is_default": index == default_index,
            }
        )
    return out


def list_input_devices() -> list[str]:
    """Kaunse mic available hain (string form — purana API)."""
    return [f"[{d['index']}] {d['name']}" for d in input_devices()]


def resolve_device(value: object) -> int | None:
    """
    User ki di hui device setting ko index mein badlo.

    Do tareeke chalte hain:
        SAARTHI_MIC_DEVICE=5          -> seedha index
        SAARTHI_MIC_DEVICE=Realtek    -> naam ka hissa (case-insensitive)

    NAAM SE MATCH KARNA ZYADA BEHTAR HAI, kyunki device index reboot
    pe ya USB mic nikaalne-lagane pe BADAL JAATA HAI. Naam usually
    same rehta hai.

    Kuch match na ho to None (system default) — crash nahi.
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # Seedha index diya hai?
    try:
        return int(text)
    except ValueError:
        pass

    # Naam se dhoondo
    needle = text.lower()
    devices = input_devices()

    for device in devices:
        if needle == device["name"].lower():
            return device["index"]
    for device in devices:
        if needle in device["name"].lower():
            return device["index"]

    log.warning(
        "SAARTHI_MIC_DEVICE='%s' se koi mic match nahi hua. "
        "System default use kar raha hun. "
        "Available: %s",
        text,
        ", ".join(f"[{d['index']}] {d['name']}" for d in devices) or "koi nahi",
    )
    return None


def describe_device(index: int | None) -> str:
    """Device ka padhne layak naam — hardware_check ke liye."""
    devices = input_devices()

    if index is None:
        default = next((d for d in devices if d["is_default"]), None)
        if default:
            return f"[{default['index']}] {default['name']} (system default)"
        return "system default"

    match = next((d for d in devices if d["index"] == index), None)
    if match:
        return f"[{match['index']}] {match['name']}"
    return f"[{index}] (is index pe koi input device nahi mila)"


# ----------------------------------------------------------------------
#  Recorder — mic se audio lena
# ----------------------------------------------------------------------


class AudioError(Exception):
    """Audio layer ki problem."""


class Recorder:
    """
    Microphone se audio record karta hai.

    Do tareeke:
        record_fixed(seconds)      -> fixed time
        record_until_silence()     -> bolo, chup ho jao, bas ho gaya
    """

    def __init__(self, config: AudioConfig | None = None, device: int | None = None):
        self.config = config or AudioConfig()
        # `device` param jeetta hai, warna config se lo (jo .env se aata
        # hai). Pehle config ka device dekha hi nahi jaata tha — isliye
        # SAARTHI_MIC_DEVICE set karne ka koi asar nahi hota tha.
        self.device = device if device is not None else self.config.device

    def peak_level(self, seconds: float = 0.25) -> int:
        """
        Abhi ka peak level (0-32767) — LIVE level meter ke liye.

        Ye diagnostic ke liye bahut zaroori hai: user ko DIKHNA chahiye
        ki uski awaaz register ho rahi hai ya nahi. Recording ke BAAD
        ek number dikhana kaafi nahi — tab tak der ho chuki hoti hai.
        """
        self._require_audio()

        frames = max(1, int(seconds * self.config.sample_rate))
        audio = sd.rec(
            frames,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            device=self.device,
        )
        sd.wait()

        flat = audio.ravel() if hasattr(audio, "ravel") else audio
        if len(flat) == 0:
            return 0
        try:
            return int(abs(flat).max())
        except Exception:  # noqa: BLE001
            return max(abs(int(sample)) for sample in flat)

    def _require_audio(self) -> None:
        if not is_audio_available():
            raise AudioError(audio_setup_help())

    # ------------------------------------------------------------------

    def record_fixed(self, seconds: float):
        """Fixed time ke liye record karo."""
        self._require_audio()

        frames = int(seconds * self.config.sample_rate)
        audio = sd.rec(
            frames,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            device=self.device,
        )
        sd.wait()
        return audio.ravel() if hasattr(audio, "ravel") else audio

    def record_until_silence(
        self,
        on_status=None,
    ):
        """
        Record karo jab tak banda chup na ho jaaye.

        Args:
            on_status: callback(DetectorStatus) — UI ko live update
                       dene ke liye ("sun raha hun...")

        Returns:
            (audio, DetectorStatus) — kuch bola nahi to audio None
        """
        self._require_audio()

        detector = SilenceDetector(self.config)
        collected: list = []
        final_status = DetectorStatus(state=ListenState.WAITING)

        stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="int16",
            blocksize=self.config.chunk_samples,
            device=self.device,
        )

        with stream:
            total_chunks = 0
            hard_limit = (
                self.config.max_chunks
                + self.config.start_timeout_chunks
                + self.config.calibration_chunks
                + 10
            )

            while total_chunks < hard_limit:
                total_chunks += 1

                chunk, overflowed = stream.read(self.config.chunk_samples)
                if overflowed:
                    log.debug("Audio overflow — chunk gir gaya")

                flat = chunk.ravel() if hasattr(chunk, "ravel") else chunk
                status = detector.feed(flat)
                final_status = status

                if on_status is not None:
                    on_status(status)

                # Calibration ka audio nahi rakhna. Bolna shuru hone se
                # pehle ka thoda audio rakhte hain (pehla shabd na kate).
                if detector.state in (ListenState.WAITING, ListenState.SPEAKING):
                    collected.append(flat)
                    # WAITING mein buffer chhota rakho
                    if detector.state == ListenState.WAITING:
                        keep = self.config.speech_start_chunks + 3
                        if len(collected) > keep:
                            collected = collected[-keep:]

                if status.is_finished:
                    break

        if not status.got_speech or not collected:
            return None, final_status

        if HAS_NUMPY:
            audio = np.concatenate(collected)
        else:
            audio = [sample for part in collected for sample in part]

        return audio, final_status


# ----------------------------------------------------------------------
#  Playback
# ----------------------------------------------------------------------

# System audio players — sounddevice na ho to inse kaam chalega
SYSTEM_PLAYERS: list[tuple[str, list[str]]] = [
    ("aplay", ["aplay", "-q"]),               # Linux ALSA
    ("paplay", ["paplay"]),                   # Linux PulseAudio
    ("afplay", ["afplay"]),                   # macOS
    ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("play", ["play", "-q"]),                 # sox
]


def find_system_player() -> list[str] | None:
    """Koi system audio player available hai?"""
    for binary, command in SYSTEM_PLAYERS:
        if shutil.which(binary):
            return command
    return None


def play_wav(path: str | Path) -> bool:
    """
    WAV file bajao.

    Pehle sounddevice, phir system player, phir Windows fallback.
    Returns: baja ya nahi
    """
    file_path = Path(path)
    if not file_path.exists():
        log.warning("Audio file nahi mili: %s", file_path)
        return False

    # 1. sounddevice
    if is_audio_available():
        try:
            audio, sample_rate = load_wav(file_path)
            sd.play(audio, samplerate=sample_rate)
            sd.wait()
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("sounddevice playback fail: %s", exc)

    # 2. System player
    player = find_system_player()
    if player:
        try:
            subprocess.run(
                player + [str(file_path)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("System player fail: %s", exc)

    # 3. Windows
    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(str(file_path), winsound.SND_FILENAME)
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("winsound fail: %s", exc)

    log.warning("Audio bajane ka koi tareeka nahi mila")
    return False
