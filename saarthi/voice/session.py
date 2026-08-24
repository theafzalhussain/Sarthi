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


TECHNICAL NOTE:
    Audio I/O BLOCKING hai (mic se padhna, bolna). Agent ASYNC hai.
    Isliye blocking kaam `asyncio.to_thread` mein chalate hain, warna
    pura event loop ruk jaata hai.


IMAANDAAR LIMITATION:
    Barge-in support nahi hai — jab agent bol raha ho, tu beech mein
    tok ke nahi rok sakta. Uske liye echo cancellation chahiye hoti hai
    jo kaafi mushkil hai. Abhi: agent bolega, phir sunega.
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
    Recorder,
    is_audio_available,
)
from .stt import WhisperConfig, WhisperSTT, is_stt_available, stt_setup_help
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

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        import os

        def _bool(key: str, default: bool) -> bool:
            raw = os.getenv(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "haan", "y"}

        return cls(
            audio=AudioConfig.from_env(),
            whisper=WhisperConfig.from_env(),
            tts=TTSConfig.from_env(),
            wake=WakeConfig.from_env(),
            speak_replies=_bool("VOICE_SPEAK_REPLIES", True),
            voice_confirmations=_bool("VOICE_CONFIRMATIONS", True),
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

        self.running = False

    # ------------------------------------------------------------------
    #  Setup
    # ------------------------------------------------------------------

    def readiness(self) -> tuple[bool, list[str]]:
        """
        Voice mode chal sakta hai?

        Returns: (ready, problems)
        """
        problems: list[str] = []

        if not is_audio_available():
            problems.append("Mic available nahi hai")
        if not is_stt_available():
            problems.append("faster-whisper install nahi hai")
        if not self.agent.brain.is_ready:
            problems.append("Koi LLM API key nahi hai")

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
                self.on_event("calibrating", "shor naap raha hun (aadha second)...")

        elif state == ListenState.WAITING:
            if first_time:
                self.on_event("listening", "AB BOL — sun raha hun")
            elif status.loudness > status.threshold * 0.4:
                # Awaaz aa rahi hai par threshold se kam — user ko batao
                self.on_event(
                    "quiet",
                    f"awaaz aa rahi hai par kam hai "
                    f"({status.loudness:.0f} / chahiye {status.threshold:.0f}) "
                    f"— zor se bol",
                )

        elif state == ListenState.SPEAKING:
            if first_time:
                self.on_event("listening", "sun raha hun...")

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
                self.on_event("quiet", "kuch sunai nahi diya")
            return None

        if status.state == ListenState.TOO_LONG:
            self.on_event("info", "bahut lamba bola, jitna suna usi pe kaam karta hun")

        # --- Transcribe (blocking -> thread mein) ---
        self.on_event("thinking", "samajh raha hun...")

        try:
            result = await asyncio.to_thread(
                self.stt.transcribe, audio, self._extra_words
            )
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", f"Samajh nahi paya: {exc}")
            return None

        # Debug: correction dikhao
        if result.correction and result.correction.changes:
            self.on_event(
                "corrected",
                f'suna: "{result.raw_text}" -> samjha: "{result.text}"',
            )

        if not result.is_usable:
            self.on_event("unclear", result.reject_reason)
            return None

        self.on_event("heard", result.text)
        return result.text

    async def speak(self, text: str) -> None:
        """Bolo (blocking -> thread mein)."""
        if not text or not self.config.speak_replies:
            return
        try:
            await asyncio.to_thread(self.tts.say, text)
        except Exception as exc:  # noqa: BLE001 — awaaz fail ho to session na ruke
            log.warning("TTS fail: %s", exc)

    # ------------------------------------------------------------------
    #  Voice confirmation
    # ------------------------------------------------------------------

    async def voice_confirm(self, action: str, details: dict) -> bool:
        """
        Risky kaam ki confirmation — bolke.

        Agent puchega, tu "haan" ya "nahi" bolega.

        FAIL SAFE: samajh na aaye to NAHI. Do baar try karta hai,
        phir mana kar deta hai. Chup-chaap paise nahi jaane chahiye.
        """
        # Sawaal banao
        question_parts = [f"Ruk ja. {action}."]
        for key, value in list(details.items())[:3]:
            question_parts.append(f"{key} {value}.")
        question_parts.append("Karu? Haan ya nahi bol.")
        question = " ".join(question_parts)

        self.on_event("confirm", question)
        await self.speak(question)

        for attempt in range(self.config.max_retries):
            answer = await self.listen_once()

            if answer is None:
                if attempt + 1 < self.config.max_retries:
                    await self.speak("Sunai nahi diya. Haan ya nahi bol.")
                continue

            lowered = answer.strip().lower()

            # Saaf mana
            if any(
                word in lowered
                for word in ("nahi", "nahin", "mat", "ruk", "cancel", "no", "band")
            ):
                self.on_event("denied", "nahi kar raha")
                await self.speak("Theek hai, nahi kar raha.")
                return False

            # Saaf haan
            if is_affirmative(answer):
                self.on_event("approved", "kar raha hun")
                return True

            # Kuch aur bola — dobara pucho
            if attempt + 1 < self.config.max_retries:
                await self.speak("Samajh nahi aaya. Saaf haan ya nahi bol.")

        # FAIL SAFE
        self.on_event("denied", "confirmation nahi mili, isliye nahi kiya")
        await self.speak("Confirm nahi hua, isliye nahi kar raha.")
        return False

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

        await self.agent.start_session()
        await self.refresh_vocabulary()

        # Model pehle load kar lo — warna pehli command pe user
        # 30 second wait karega aur lagega hang ho gaya
        self.on_event("info", "Whisper model load ho raha hai...")
        try:
            await asyncio.to_thread(self.stt.load)
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", f"Model load nahi hua: {exc}")
            return

        self.running = True
        self.on_event("ready", "Bol bhai, sun raha hun.")
        await self.speak("Ready hun bhai.")

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

                # --- Band karne wale shabd ---
                if text.strip().lower().strip(".!?") in (
                    "band karo", "bandh karo", "band kar", "quit", "exit",
                    "bye", "khatam", "stop", "ruk ja",
                ):
                    await self.speak("Theek hai, bye bhai.")
                    break

                # --- 3. Agent se kaam karwao ---
                self.on_event("working", "kaam kar raha hun...")
                result = await self.agent.run_turn(text)

                # --- 4. Jawab bolo ---
                reply = result.error or result.reply
                self.on_event("reply", reply)
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
                self.on_event("info", "rok diya")
                break
            except Exception as exc:  # noqa: BLE001 — session kabhi crash na ho
                log.exception("Voice loop mein problem")
                self.on_event("error", f"Kuch gadbad: {exc}")
                continue

        self.running = False
        self.wake.close()
        self.on_event("info", "Voice session band")

    def stop(self) -> None:
        """Loop rok do."""
        self.running = False

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    def status(self) -> str:
        """CLI ke liye voice status."""
        lines = ["VOICE:"]
        lines.append(self.stt.status())
        lines.append(self.tts.status())
        lines.append(f"  Wake: {self.wake.name} — {self.wake.description}")

        reason = self.wake.unavailable_reason()
        if reason:
            lines.append(f"        ({reason})")

        lines.append(
            f"  Mic: {'available' if is_audio_available() else 'available nahi'}"
        )

        if self._extra_words:
            preview = ", ".join(self._extra_words[:6])
            lines.append(f"  Vocabulary boost: {preview} ...")

        return "\n".join(lines)
