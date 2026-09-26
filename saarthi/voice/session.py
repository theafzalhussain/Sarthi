"""
Voice Session — sab kuch yahan judta hai.

    [wake]  Enter dabao / "jarvis" bolo
       |
    [sun]   mic se record, chup hone pe apne aap ruk jaata hai
       |
    [samajh] Whisper + Hinglish correction
       |
    [karo]  agent.run_turn()  <- Phase 1 ka pura agent
       |
    [bolo]  TTS se jawab


EK ACCHI CHEEZ (Pillar #1 aur #2 ka milaap):

    Whisper ko jo `extra_words` bhejte hain, wo MEMORY aur SKILLS se
    banate hain:

        memory  -> "mummy ka number" se "mummy" nikal aata hai
        skills  -> "bijli ka bill" seekha hua kaam

    Matlab jitna tu agent ko sikhaayega, utna ACCHA wo tujhe SUNEGA.
    Ye compounding fayda hai — normal voice assistants mein nahi hota.


PHASE 5A UPGRADES (naye powers):
    1. STREAMING TTS  — LLM ka pehla sentence aate hi bolna shuru,
       poore jawab ka intezaar nahi. Order kabhi nahi badalta.
    2. BARGE-IN       — agent ke bolte waqt bol do, wo TURANT chup
       ho jaata hai (VOICE_BARGE_IN=true se on; headphone pe best).
    3. HINGLISH VOICE — Hinglish jawab Hindi neural voice (Madhur) se
       Devanagari mein bolta hai — "bhai, 2500 ka bill bhar do" ab
       "भाई, दो हज़ार पांच सौ का बिल भर दो" jaisa sunai deta hai.


TECHNICAL NOTE:
    Audio I/O BLOCKING hai (mic se padhna, bolna). Agent ASYNC hai.
    Isliye blocking kaam `asyncio.to_thread` mein chalate hain, warna
    pura event loop ruk jaata hai.


IMAANDAAR LIMITATION:
    Barge-in speaker pe echo false-trigger de sakta hai (AEC nahi hai)
    — isliye wo DEFAULT OFF hai. Headphone pe bharosemand hai. Bina
    barge-in ke: agent bolega, phir sunega.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..agent import Agent
from ..tools.safety import is_affirmative
from .audio import (
    AudioConfig,
    AudioError,
    DetectorStatus,
    ListenState,
    MicMonitor,
    Recorder,
    is_audio_available,
)
from .stt import WhisperConfig, WhisperSTT, is_stt_available, stt_setup_help
from .streaming import StreamSpeaker
from .tts import TTSConfig, TTSEngine
from .wake import WakeConfig, WakeDetector, create_wake_detector

log = logging.getLogger("saarthi.voice.session")


# ======================================================================
#  Config
# ======================================================================


@dataclass
class VoiceConfig:
    """Poore voice session ki settings."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)

    # Agent ka jawab bolna hai?
    speak_replies: bool = True

    # Risky kaam ki confirmation bolke leni hai?
    voice_confirmations: bool = True

    # Kitni baar dobara puchein jab samajh na aaye
    max_retries: int = 2

    # STREAMING TTS (Phase 5A): LLM ka jawab sentence-by-sentence bolna
    # — poore jawab ka intezaar nahi. Pehli awaaz ~1-2 sec mein.
    streaming_tts: bool = True

    # BARGE-IN (Phase 5A): agent ke bolte waqt beech mein tokna.
    # DEFAULT OFF — speakers pe echo false-trigger de sakta hai.
    # HEADPHONE use karte ho to true karo, experience real ho jaata hai.
    barge_in: bool = False

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        import os

        def _bool(key: str, default: bool) -> bool:
            raw = os.getenv(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "haan", "y", "on"}

        return cls(
            audio=AudioConfig.from_env(),
            whisper=WhisperConfig.from_env(),
            tts=TTSConfig.from_env(),
            wake=WakeConfig.from_env(),
            speak_replies=_bool("VOICE_SPEAK_REPLIES", True),
            voice_confirmations=_bool("VOICE_CONFIRMATIONS", True),
            streaming_tts=_bool("VOICE_STREAMING_TTS", True),
            barge_in=_bool("VOICE_BARGE_IN", False),
        )


# ======================================================================
#  Session
# ======================================================================


class VoiceSession:
    """
    Voice se agent chalane wala loop.

    Use:
        session = VoiceSession(agent)
        await session.run()
    """

    def __init__(
        self,
        agent: Agent,
        config: VoiceConfig | None = None,
        on_event=None,
    ):
        """
        Args:
            agent: Phase 1 ka agent
            config: Voice settings
            on_event: callback(kind, text) — UI update ke liye
        """
        self.agent = agent
        self.config = config or VoiceConfig()
        self.on_event = on_event or (lambda kind, text: None)

        self.stt = WhisperSTT(self.config.whisper)
        self.tts = TTSEngine(self.config.tts)
        self.recorder = Recorder(self.config.audio)
        self.wake: WakeDetector = create_wake_detector(
            self.config.wake, self.config.audio
        )

        # Whisper ko bias karne wale words (memory + skills se)
        self._extra_words: list[str] = []

        # STREAMING TTS — LLM ke sentence bolte jaata hai (Phase 5A)
        self.speaker = StreamSpeaker(self.tts, enabled=self.config.streaming_tts)

        self.running = False

    # ------------------------------------------------------------------
    #  Setup
    # ------------------------------------------------------------------

    def readiness(self) -> tuple[bool, list[str]]:
        """
        Can voice mode run?

        Returns: (ready, problems)
        """
        problems: list[str] = []

        if not is_audio_available():
            problems.append("Microphone not available")
        if not is_stt_available():
            problems.append("faster-whisper not installed")
        if not self.agent.brain.is_ready:
            problems.append("No LLM API key configured")

        return (len(problems) == 0, problems)

    async def refresh_vocabulary(self) -> list[str]:
        """
        Memory aur skills se Whisper ke liye vocabulary banao.

        Yahi wo cheez hai jo agent ko time ke saath BEHTAR sunne wala
        banati hai — jitna sikhaayega, utna accha samjhega.
        """
        words: list[str] = []

        # 1. Skills ke naam — user inhi shabdon se bulaayega
        try:
            skills = await self.agent.skills.list_skills(limit=25)
            words.extend(skill.name for skill in skills)
        except Exception as exc:  # noqa: BLE001
            log.debug("Skills se vocabulary nahi mili: %s", exc)

        # 2. Memory se naam (contacts wagairah)
        try:
            facts = await self.agent.memory.all_facts(limit=40)
            for fact in facts:
                # "mummy ka number" -> "mummy"
                first = fact.key.split()[0] if fact.key.split() else ""
                if len(first) > 2:
                    words.append(first)
        except Exception as exc:  # noqa: BLE001
            log.debug("Memory se vocabulary nahi mili: %s", exc)

        # Duplicates hatao, order rakho
        seen: set[str] = set()
        unique: list[str] = []
        for word in words:
            key = word.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(word.strip())

        self._extra_words = unique[:30]
        log.debug("Voice vocabulary: %s", self._extra_words)
        return self._extra_words

    # ------------------------------------------------------------------
    #  Listen
    # ------------------------------------------------------------------

    def _report_listening(self, status: DetectorStatus) -> None:
        """
        Recording ke dauraan UI update.

        ⚠️ YAHAN EK ASLI UX BUG THA.

        Pehle sirf SPEAKING aur CALIBRATING report hote the. WAITING
        (calibration ke baad, bolne ka intezaar) pe KUCH NAHI dikhta tha.

        User ko ye dikhta tha:
            ⋯ shor naap raha hun...   (x15)
            [10 second tak kuch nahi]
            · kuch sunai nahi diya

        User ko lagta tha HANG ho gaya — usko pata hi nahi chalta ki
        AB BOLNA HAI. Voice mode pura toota hua lagta tha.

        Ab: WAITING pe saaf "AB BOL" dikhta hai, aur loudness vs
        threshold bhi — taaki user dekh sake ki awaaz kam pad rahi hai.
        Aur calibration ka spam ek hi baar dikhta hai.
        """
        state = status.state

        # Ek hi state ko baar-baar report na karo (spam hata do)
        last = getattr(self, "_last_listen_state", None)
        first_time = state != last
        self._last_listen_state = state

        if state == ListenState.CALIBRATING:
            if first_time:
                self.on_event("calibrating", "Calibrating ambient noise...")

        elif state == ListenState.WAITING:
            if first_time:
                self.on_event("listening", "Listening — speak now")

        elif state == ListenState.SPEAKING:
            if first_time:
                self.on_event("listening", "Listening...")

    async def listen_once(self) -> str | None:
        """
        Ek baar suno aur text banao.

        Returns: text, ya None (kuch samajh nahi aaya)
        """
        # --- Record (blocking -> thread mein) ---
        try:
            audio, status = await asyncio.to_thread(
                self.recorder.record_until_silence, self._report_listening
            )
        except AudioError as exc:
            self.on_event("error", str(exc))
            return None
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", f"Recording fail: {exc}")
            return None

        if audio is None:
            if status.state == ListenState.TIMEOUT:
                self.on_event("quiet", "Nothing heard")

            elif status.state == ListenState.NO_AUDIO:
                self.on_event(
                    "error",
                    "No audio from microphone (receiving zeros) — "
                    "this is not a volume issue, check your audio pipeline.\n"
                    "    Run: python hardware_check.py --mic-stream",
                )
            return None

        if status.state == ListenState.TOO_LONG:
            self.on_event("info", "Utterance too long — processing what was captured")

        # --- Transcribe (blocking -> thread) ---
        self.on_event("thinking", "Processing speech...")

        try:
            result = await asyncio.to_thread(
                self.stt.transcribe, audio, self._extra_words
            )
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", f"Transcription failed: {exc}")
            return None

        # Debug: show correction
        if result.correction and result.correction.changes:
            self.on_event(
                "corrected",
                f'heard: "{result.raw_text}" -> understood: "{result.text}"',
            )

        if not result.is_usable:
            self.on_event("unclear", result.reject_reason)
            return None

        self.on_event("heard", result.text)
        return result.text

    async def speak(self, text: str) -> None:
        """
        Bolo (blocking -> thread mein).

        BARGE-IN on hai to bolte waqt mic monitor chalta hai — user
        beech mein bole to playback turant ruk jaata hai.
        """
        if not text or not self.config.speak_replies:
            return
        try:
            if self.config.barge_in and self.tts.has_voice:
                await self._speak_with_barge_in(text)
            else:
                await asyncio.to_thread(self.tts.say, text)
        except Exception as exc:  # noqa: BLE001 — awaaz fail ho to session na ruke
            log.warning("TTS fail: %s", exc)

    async def _speak_with_barge_in(self, text: str) -> None:
        """
        Bolo + saath mein mic suno. User bole to TURANT chup.

        MicMonitor halka hai (background stream, RMS check) — event loop
        block nahi hota. Mic na mile to normal speak hi ho jaata hai.
        """
        monitor = MicMonitor(self.config.audio)
        if not monitor.start():
            # Mic monitor nahi chala — barge-in nahi, seedha bolo
            await asyncio.to_thread(self.tts.say, text)
            return

        task = asyncio.create_task(asyncio.to_thread(self.tts.say, text))
        interrupted = False
        try:
            while not task.done():
                await asyncio.sleep(0.08)
                if monitor.should_interrupt():
                    interrupted = True
                    self.tts.stop_speaking()
                    self.on_event("barge_in", "User interrupted — stopped speaking")
                    break
        finally:
            monitor.stop()
            try:
                # Task khatam hone do (cancel flag pe khud ruk jaayega)
                await asyncio.wait_for(asyncio.shield(task), timeout=10)
            except Exception:  # noqa: BLE001
                pass

        if interrupted:
            self.on_event("info", "Aap ne roka — sun raha hun")

    # ------------------------------------------------------------------
    #  Voice confirmation
    # ------------------------------------------------------------------

    async def voice_confirm(self, action: str, details: dict) -> bool:
        """
        Voice confirmation for risky actions.

        Agent asks, user says "yes" or "no".
        FAIL SAFE: if unclear, default is NO.
        """
        question_parts = [f"Hold on. {action}."]
        for key, value in list(details.items())[:3]:
            question_parts.append(f"{key}: {value}.")
        question_parts.append("Should I proceed? Say yes or no.")
        question = " ".join(question_parts)

        self.on_event("confirm", question)
        await self.speak(question)

        for attempt in range(self.config.max_retries):
            answer = await self.listen_once()

            if answer is None:
                if attempt + 1 < self.config.max_retries:
                    await self.speak("Didn't catch that. Say yes or no.")
                continue

            lowered = answer.strip().lower()

            # Clear denial
            if any(
                word in lowered
                for word in ("nahi", "nahin", "mat", "ruk", "cancel", "no", "band", "stop", "don't")
            ):
                self.on_event("denied", "Action cancelled")
                await self.speak("Got it, cancelled.")
                return False

            # Clear approval
            if is_affirmative(answer):
                self.on_event("approved", "Proceeding")
                return True

            # Unclear — ask again
            if attempt + 1 < self.config.max_retries:
                await self.speak("Didn't understand. Please say yes or no clearly.")

        # FAIL SAFE
        self.on_event("denied", "No confirmation received — action skipped")
        await self.speak("No confirmation, skipping.")
        return False

    # ------------------------------------------------------------------
    #  Streaming TTS wiring
    # ------------------------------------------------------------------

    def _attach_stream_tts(self) -> None:
        """
        Agent ke `on_output` mein apna stream hook lagao.

        Agent run_turn ke dauraan ("stream", token) emit karta hai —
        wahi tokens speaker ko jaate hain aur sentences bolte jaate
        hain. Pehla sentence aate hi awaaz shuru — poora jawab ka
        intezaar nahi.

        Pehla original handler PRESERVE hota hai (CLI ne jo lagaya tha
        wo bhi chalta rahega).
        """
        original = getattr(self.agent, "on_output", None)

        def handler(kind: str, text: str) -> None:
            if kind == "stream" and text:
                self.speaker.feed(text)
            if original is not None:
                try:
                    original(kind, text)
                except Exception:  # noqa: BLE001
                    pass

        try:
            self.agent.on_output = handler
        except Exception as exc:  # noqa: BLE001
            log.warning("Streaming TTS attach fail: %s", exc)

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Voice loop chalao.

        Ctrl+C ya "band karo" pe rukta hai.
        """
        ready, problems = self.readiness()
        if not ready:
            for problem in problems:
                self.on_event("error", problem)
            if not is_stt_available():
                self.on_event("info", stt_setup_help())
            return

        # Agent ko voice confirmations do
        if self.config.voice_confirmations:
            self.agent.confirm = self.voice_confirm

        # STREAMING TTS: agent ke stream tokens ko speaker mein daalo
        # (purana on_output preserve hota hai — CLI/web bhi chalta rahega)
        if self.config.streaming_tts:
            self._attach_stream_tts()

        await self.agent.start_session()
        await self.refresh_vocabulary()

        # Model pehle load kar lo — warna pehli command pe user
        # 30 second wait karega aur lagega hang ho gaya
        self.on_event("info", "Loading Whisper model...")
        try:
            await asyncio.to_thread(self.stt.load)
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", f"Model failed to load: {exc}")
            return

        self.running = True
        self.on_event("ready", "Ready — press Enter, then speak.")
        await self.speak("Ready.")

        while self.running:
            try:
                # --- 1. Wake (blocking -> thread mein) ---
                woken = await asyncio.to_thread(self.wake.wait_for_wake)
                if not woken:
                    break

                # --- 2. Suno ---
                text = await self.listen_once()
                if text is None:
                    continue

                # --- Stop commands ---
                if text.strip().lower().strip(".!?") in (
                    "band karo", "bandh karo", "band kar", "quit", "exit",
                    "bye", "khatam", "stop", "ruk ja", "stop listening",
                ):
                    await self.speak("Goodbye.")
                    break

                # --- 3. Process with agent ---
                self.on_event("working", "Processing...")
                self.speaker.reset()  # naya turn — purana buffer saaf
                result = await self.agent.run_turn(text)

                # --- 4. Jawab bolo ---
                reply = result.error or result.reply
                self.on_event("reply", reply)

                if self.config.streaming_tts and not result.error:
                    # Streaming: zyada-tar sentences bol chuka — bache
                    # hue bol do aur worker ke khatam hone ka intezaar
                    await self.speaker.finish()
                    # Safety net: streaming se kuch nahi bola gaya
                    # (provider ne stream nahi diya etc.) to poora bolo
                    if not self.speaker.spoken_count and reply:
                        await self.speak(reply)
                else:
                    await self.speak(reply)

                # Naya kuch seekha ho to vocabulary update karo
                if any(
                    name in (result.tool_calls or [])
                    for name in ("skill_yaad_kar_le", "yaad_rakho")
                ):
                    await self.refresh_vocabulary()

                # Free tier tokens bachao
                self.agent.trim_history()

            except KeyboardInterrupt:
                self.on_event("info", "Stopped")
                break
            except Exception as exc:  # noqa: BLE001
                log.exception("Voice loop error")
                self.on_event("error", f"Error: {exc}")
                continue

        self.running = False
        self.wake.close()
        self.on_event("info", "Voice session ended")

    def stop(self) -> None:
        """Loop rok do."""
        self.running = False

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    def status(self) -> str:
        """Voice status for CLI display."""
        lines = ["VOICE:"]
        lines.append(self.stt.status())
        lines.append(self.tts.status())
        lines.append(f"  Wake: {self.wake.name} — {self.wake.description}")

        reason = self.wake.unavailable_reason()
        if reason:
            lines.append(f"        ({reason})")

        lines.append(
            f"  Mic: {'available' if is_audio_available() else 'not available'}"
        )

        # Phase 5A naye features
        tts_mode = "streaming" if self.config.streaming_tts else "full-reply"
        barge = "on" if self.config.barge_in else "off (VOICE_BARGE_IN=true)"
        lines.append(f"  Speech: {tts_mode} TTS · barge-in {barge}")

        if self._extra_words:
            preview = ", ".join(self._extra_words[:6])
            lines.append(f"  Vocabulary: {preview} ...")

        return "\n".join(lines)
