"""
SAARTHI Voice — bolke agent chalao.

    hinglish_asr.py  -> PILLAR #1 voice pe: biasing + correction
    audio.py         -> mic recording, silence detection, playback
    stt.py           -> Whisper (offline, free)
    tts.py           -> awaaz (piper/espeak/say/pyttsx3/null)
    wake.py          -> push-to-talk / energy / porcupine
    session.py       -> pura loop

Sab OFFLINE aur FREE hai. LLM ke liye internet chahiye, voice ke liye nahi.

Use:
    from saarthi.agent import Agent
    from saarthi.voice import VoiceSession, VoiceConfig

    agent = Agent()
    session = VoiceSession(agent, VoiceConfig.from_env())
    await session.run()

Sab dependencies OPTIONAL hain — install na hon to clear message milta
hai, crash nahi hota.
"""

from .audio import (
    HAS_NUMPY,
    HAS_SOUNDDEVICE,
    AudioConfig,
    AudioError,
    DetectorStatus,
    ListenState,
    Recorder,
    describe_device,
    input_devices,
    resolve_device,
    SilenceDetector,
    audio_setup_help,
    is_audio_available,
    list_input_devices,
    load_wav,
    play_wav,
    rms,
    save_wav,
)
from .hinglish_asr import (
    CorrectionResult,
    build_initial_prompt,
    correct_transcript,
    looks_like_garbage,
)
from .session import VoiceConfig, VoiceSession
from .stt import (
    HAS_WHISPER,
    MODEL_INFO,
    STTError,
    TranscriptResult,
    WhisperConfig,
    WhisperSTT,
    is_stt_available,
    recommend_model_size,
    stt_setup_help,
)
from .tts import (
    TTSConfig,
    TTSEngine,
    prepare_text_for_speech,
)
from .wake import (
    HAS_PORCUPINE,
    WakeConfig,
    WakeDetector,
    available_wake_modes,
    create_wake_detector,
)

__all__ = [
    # Session (main entry point)
    "VoiceSession",
    "VoiceConfig",
    # Hinglish ASR — PILLAR #1
    "correct_transcript",
    "CorrectionResult",
    "build_initial_prompt",
    "looks_like_garbage",
    # Audio
    "AudioConfig",
    "Recorder",
    "describe_device",
    "input_devices",
    "resolve_device",
    "SilenceDetector",
    "ListenState",
    "DetectorStatus",
    "AudioError",
    "is_audio_available",
    "audio_setup_help",
    "list_input_devices",
    "save_wav",
    "load_wav",
    "play_wav",
    "rms",
    "HAS_SOUNDDEVICE",
    "HAS_NUMPY",
    # STT
    "WhisperSTT",
    "WhisperConfig",
    "TranscriptResult",
    "STTError",
    "is_stt_available",
    "stt_setup_help",
    "recommend_model_size",
    "MODEL_INFO",
    "HAS_WHISPER",
    # TTS
    "TTSEngine",
    "TTSConfig",
    "prepare_text_for_speech",
    # Wake
    "WakeDetector",
    "WakeConfig",
    "create_wake_detector",
    "available_wake_modes",
    "HAS_PORCUPINE",
]
