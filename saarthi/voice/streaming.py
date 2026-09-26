"""
Streaming TTS — LLM ka jawab AATE HI bolna shuru, poora hone ka intezaar nahi.

PEHLE KAISE THA:
    agent ka poora jawab bana -> phir TTS -> phir bolna shuru.
    Lambe jawab pe user 5-10 second chup chaap dekhta tha.

AB KAISE HAI:
    LLM stream se pehla sentence poora hote hi TTS queue mein chala
    jaata hai. Beech ke sentences bolte-bolte naye bante rehte hain.
    User ko pehli awaaz ~1-2 second mein mil jaati hai.

    LLM stream ──token──token──token──┐
                                      ▼
                          SentenceBuffer (sentence detect)
                                      │ poora hua?
                                      ▼
                        StreamSpeaker queue ──► TTS #1 bol raha
                                      │         TTS #2 line mein
                                      ▼
                                 (order kabhi nahi badalta)


DESIGN NOTE — order aur cancel:
    1. Sentences KABHI overlapping nahi bolte — ek hi worker task
       sequentially bolta hai. Pehle wale version mein har sentence
       ka alag task tha (overlapping + order shuffle hota tha).
    2. `cancel()` naya turn shuru hone pe purana speech turant rokta
       hai — warna purana jawab naya jawab chhaa jaata tha.
    3. TTS blocking hai, isliye worker `asyncio.to_thread` use karta
       hai — event loop kabhi block nahi hota.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from .hinglish_tts import SentenceBuffer, split_into_sentences

log = logging.getLogger("saarthi.voice.streaming")


class StreamSpeaker:
    """
    Async sentence-queue speaker — voice mode + web UI dono use karte hain.

    Use (voice session / jarvis):
        speaker = StreamSpeaker(tts_engine)

        # LLM stream ke saath:
        speaker.feed(chunk.delta)          # token aaya

        # Turn khatam:
        await speaker.finish()             # bache hue bol do

        # Naya turn (purana bolna chhod):
        speaker.cancel()
    """

    def __init__(self, tts_engine, enabled: bool = True):
        self.tts = tts_engine
        self.enabled = enabled
        self.buffer = SentenceBuffer()

        # Queue: sentences ki line — worker isse bolta hai
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

        # thread-safe cancel flag — TTS thread bhi isko dekhta hai
        self._cancel_event = threading.Event()

        # stats (UI/status ke liye)
        self.spoken_count = 0
        self.cancelled_count = 0

    # ------------------------------------------------------------------
    #  Feeding (LLM stream side)
    # ------------------------------------------------------------------

    def feed(self, delta: str) -> list[str]:
        """
        Naya token do. Complete sentence bana to queue mein daal do.

        Returns: jo sentences queue hue (debug/UI ke liye)
        """
        if not self.enabled or not delta:
            return []

        queued: list[str] = []
        for sentence in self.buffer.feed(delta):
            self._enqueue(sentence)
            queued.append(sentence)
        return queued

    def feed_text(self, text: str) -> list[str]:
        """Poora text ek saath (non-streaming agents ke liye)."""
        if not self.enabled or not text:
            return []

        queued: list[str] = []
        for sentence in split_into_sentences(
            text, self.buffer.min_chars, self.buffer.max_chars
        ):
            self._enqueue(sentence)
            queued.append(sentence)
        return queued

    def _enqueue(self, sentence: str) -> None:
        if not sentence.strip():
            return
        self._ensure_worker()
        try:
            self._queue.put_nowait(sentence)
        except Exception as exc:  # noqa: BLE001
            log.warning("Sentence queue fail: %s", exc)

    # ------------------------------------------------------------------
    #  Worker — ek hi task, sequential bolna (order guaranteed)
    # ------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._cancel_event.clear()
            self._worker = asyncio.get_running_loop().create_task(self._run())

    async def _run(self) -> None:
        """Queue se sentences uthao aur bolo — jab tak None na aaye."""
        loop = asyncio.get_running_loop()
        while True:
            sentence = await self._queue.get()
            try:
                if sentence is None:
                    return
                if self._cancel_event.is_set():
                    # Cancel ho chuka — queue saaf karo, bolo mat
                    self._drain_queue()
                    return
                try:
                    await loop.run_in_executor(None, self._speak_safe, sentence)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Sentence speak fail: %s", exc)
                self.spoken_count += 1
            finally:
                self._queue.task_done()

    def _speak_safe(self, sentence: str) -> None:
        """TTS call (THREAD mein chalta hai) — cancel flag respect karo."""
        if self._cancel_event.is_set():
            return
        try:
            # Engine ke apne cancel bhi set karo — beech playback ruk sake
            stop = getattr(self.tts, "attach_cancel_event", None)
            if stop:
                stop(self._cancel_event)
            self.tts.say(sentence)
        except Exception as exc:  # noqa: BLE001
            log.warning("TTS fail (speaker continues): %s", exc)
        finally:
            stop = getattr(self.tts, "attach_cancel_event", None)
            if stop:
                stop(None)

    def _drain_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    # ------------------------------------------------------------------
    #  Turn lifecycle
    # ------------------------------------------------------------------

    async def finish(self) -> None:
        """
        Turn khatam — bache hue text bolo aur worker ke khatam hone ka
        intezaar karo.
        """
        if not self.enabled:
            return

        rest = self.buffer.flush()
        if rest:
            self._enqueue(rest)

        # Sentinel — worker ko batao ki bas ho gaya
        self._enqueue_sentinel()

        if self._worker is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._worker), timeout=120)
            except asyncio.TimeoutError:
                log.warning("Speaker timeout — cancel kar raha hun")
                self.cancel()
            except Exception as exc:  # noqa: BLE001
                log.warning("Worker khatam hua error se: %s", exc)

    def _enqueue_sentinel(self) -> None:
        self._ensure_worker()
        try:
            self._queue.put_nowait(None)
        except Exception:  # noqa: BLE001
            pass

    def cancel(self) -> None:
        """
        Turant chup. Naya turn shuru hone se pehle call karo.

        Chalu playback rokta hai + queue saaf karta hai.
        """
        self._cancel_event.set()
        self.buffer.clear()
        self._drain_queue()
        self.cancelled_count += 1

        # Engine-level stop (playback process kill)
        stop = getattr(self.tts, "stop_speaking", None)
        if stop:
            try:
                stop()
            except Exception:  # noqa: BLE001
                pass

    def reset(self) -> None:
        """Naya turn — buffer + counter saaf, worker re-usable."""
        self.buffer.clear()
        self.spoken_count = 0

    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._worker is not None and not self._worker.done()

    def status(self) -> str:
        return (
            f"StreamSpeaker: enabled={self.enabled}, "
            f"spoken={self.spoken_count}, cancelled={self.cancelled_count}"
        )
