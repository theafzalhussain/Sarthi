"""
Telegram Bot — PHONE se ghar ke JARVIS ko command de.

SCENARIO:

    Tu bahar hai, ghar pe PC on hai. Telegram pe message:
        "bhai bijli ka bill kl due hai kya?"
    -> JARVIS (PC pe chal raha) memory dekh ke jawab deta hai.
    Voice note bhejo -> wahi kaam (whisper sun leta hai).

    Ye ROADMAP ka "Local server: phone se laptop ke agent ko baat
    karana" — par bina koi port khole, bina public IP ke. Telegram
    ka infra hi tunnel ka kaam karta hai.

DESIGN — ZERO naya dependency:

    Telegram Bot API = simple HTTPS (getUpdates long polling).
    httpx ALREADY core dep hai. python-telegram-bot ki zarurat nahi.

SECURITY (fail-safe, repo ke rules ke saath):

    1. TELEGRAM_ALLOWED_CHAT_IDS — SIRF ye chats baat kar sakte hain.
       Khaali ho to bot SABKO ignore karta hai (kisi se bhi).
    2. RISKY kaam Telegram se nahi honge — confirmation callback
       chhota aur sakht hai: risky tool aaya to bot mana kar deta hai
       ("laptop pe puch ke karo"). Payment/OTP wale rules pehle se
       hard-block hain, wo yahan bhi hain.
    3. Bot token kabhi code/repo mein nahi — sirf .env.

SETUP:

    1. Telegram pe @BotFather se bot banao -> token mila
    2. .env mein:
        TELEGRAM_BOT_TOKEN=123:abc...
        TELEGRAM_ALLOWED_CHAT_IDS=123456789
       (apna chat id @userinfobot se pata karo)
    3. jarvis.py start karo — bot background mein chal jaata hai
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("saarthi.telegram")

_TELEGRAM_BASE = "https://api.telegram.org/bot{token}"

# Voice note transcribe karne ke liye — Hinglish correction ke saath
VoiceNoteHandler = None  # lazy init


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class TelegramBot:
    """
    Long-polling Telegram bot — JARVIS ka remote control.

    Use (jarvis.py se):
        bot = TelegramBot(agent)
        await bot.start()        # background task
        ...
        await bot.stop()
    """

    def __init__(self, agent, scheduler=None):
        self.agent = agent
        self.scheduler = scheduler or getattr(agent, "scheduler", None)

        self.token = _env("TELEGRAM_BOT_TOKEN")
        self.allowed_chats: set[int] = {
            int(x) for x in _env("TELEGRAM_ALLOWED_CHAT_IDS").split(",") if x.strip()
        }

        self._client = None
        self._task: asyncio.Task | None = None
        self._offset = 0
        self.running = False

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def start(self) -> bool:
        """Bot background mein shuru. Returns: shuru hua ya nahi."""
        if not self.configured:
            log.info("TELEGRAM_BOT_TOKEN nahi hai — bot off (theek hai)")
            return False

        import httpx

        self._client = httpx.AsyncClient(timeout=40.0)

        # Token check + bot info
        me = await self._api("getMe")
        if not me or not me.get("ok"):
            log.warning("Telegram bot token galat lag raha hai — bot off")
            await self._client.aclose()
            self._client = None
            return False

        if not self.allowed_chats:
            log.warning(
                "TELEGRAM_ALLOWED_CHAT_IDS khaali hai — bot kisi ko jawab "
                "NAHI dega. Apna chat id daalo (@userinfobot se milta hai)."
            )

        self.running = True
        self._task = asyncio.get_running_loop().create_task(self._poll_loop())
        log.info(
            "Telegram bot live: @%s (allowed chats: %d)",
            me["result"].get("username", "?"),
            len(self.allowed_chats),
        )
        return True

    async def stop(self) -> None:
        self.running = False
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    # ------------------------------------------------------------------
    #  Telegram API (httpx — koi SDK nahi)
    # ------------------------------------------------------------------

    async def _api(self, method: str, payload: dict | None = None) -> dict | None:
        if self._client is None:
            return None
        try:
            url = _TELEGRAM_BASE.format(token=self.token) + f"/{method}"
            resp = await self._client.post(url, json=payload or {})
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            log.debug("Telegram API %s fail: %s", method, exc)
            return None

    async def _send(self, chat_id: int, text: str) -> None:
        """Message bhejo (4096 char limit — kaat ke bhejte hain)."""
        text = text.strip() or "..."
        for i in range(0, len(text), 4000):
            await self._api(
                "sendMessage",
                {"chat_id": chat_id, "text": text[i : i + 4000]},
            )

    # ------------------------------------------------------------------
    #  Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """getUpdates long polling — 30s block, koi error pe continue."""
        while self.running:
            try:
                data = await self._api(
                    "getUpdates",
                    {
                        "offset": self._offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                )
                if data and data.get("ok"):
                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        try:
                            await self._handle_update(update)
                        except Exception as exc:  # noqa: BLE001
                            log.warning("Update handle fail: %s", exc)
                else:
                    # API fail — thoda ruk ke dobara (spam na ho)
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Telegram poll fail (retry in 5s): %s", exc)
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    #  Update handling — ye PURE LOGIC ke kareeb hai (tests mock karte hain)
    # ------------------------------------------------------------------

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")

        if chat_id is None:
            return

        # --- SECURITY: whitelist ---
        if chat_id not in self.allowed_chats:
            log.warning("Telegram: chat %s allowed nahi — ignore", chat_id)
            return

        # Voice note?
        voice = message.get("voice") or message.get("audio")
        if voice:
            await self._handle_voice(chat_id, voice)
            return

        text = (message.get("text") or "").strip()
        if not text:
            return

        # --- Commands ---
        if text.startswith("/"):
            await self._handle_command(chat_id, text.lower())
            return

        # --- Normal command -> agent ---
        reply = await self._run_agent(text)
        await self._send(chat_id, reply)

    async def _handle_command(self, chat_id: int, text: str) -> None:
        if text.startswith("/start"):
            await self._send(
                chat_id,
                "🛕 JARVIS online.\n\n"
                "Kuch bhi pucho — jaise ghar ke agent se baat kar rahe ho.\n"
                "Voice note bhejo to wahi baat.\n\n"
                "/status — system status\n"
                "/tasks — pending reminders",
            )
        elif text.startswith("/status"):
            try:
                status = await self.agent.status()
            except Exception:  # noqa: BLE001
                status = "status nahi mila"
            await self._send(chat_id, status)
        elif text.startswith("/tasks"):
            await self._send_tasks(chat_id)
        else:
            await self._send(chat_id, "Ye command nahi pata. /start dekh lo.")

    async def _send_tasks(self, chat_id: int) -> None:
        if self.scheduler is None:
            await self._send(chat_id, "Scheduler available nahi.")
            return
        try:
            tasks = await self.scheduler.pending(limit=15)
            if not tasks:
                await self._send(chat_id, "Koi pending reminder nahi.")
                return
            lines = ["⏰ Pending reminders:"]
            for task in tasks:
                icon = "🔁" if task.recurrence != "none" else "⏰"
                lines.append(f"{icon} #{task.id} — {task.message} ({task.due_text()})")
            await self._send(chat_id, "\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            await self._send(chat_id, f"Tasks nahi mile: {exc}")

    # ------------------------------------------------------------------
    #  Agent run — risk-controlled
    # ------------------------------------------------------------------

    async def _run_agent(self, text: str) -> str:
        """
        Agent chalao aur reply text do.

        SECURITY: Telegram pe risky kaam AUTO-DENY hote hain. Payment
        waise bhi hard-block hain; yahan confirmation lo-tok bhi nahi
        (remote pe paise ka confirmation untrustworthy hai).
        """
        # Agent ka confirm temporarily swap karo — thread-safe kaafi hai
        # (ek bot loop ek waqt pe ek turn chalata hai)
        original_confirm = self.agent.confirm
        self.agent.confirm = self._telegram_confirm
        try:
            result = await self.agent.run_turn(text)
        finally:
            self.agent.confirm = original_confirm

        if result.error:
            return f"⚠️ {result.error}"
        return result.reply or "(koi jawab nahi aaya)"

    async def _telegram_confirm(self, action: str, details: dict) -> bool:
        """Telegram se risky kaam — hamesha MANA (fail-safe)."""
        log.info("Telegram risky tool block: %s", action)
        return False

    # ------------------------------------------------------------------
    #  Voice notes — sunna bhi aata hai
    # ------------------------------------------------------------------

    async def _handle_voice(self, chat_id: int, voice: dict) -> None:
        """
        Voice note download -> whisper transcribe -> agent.

        Whisper na ho to saaf batao (chup nahi rehna).
        """
        file_id = voice.get("file_id")
        if not file_id:
            return

        # 1. STT available?
        try:
            from .voice.stt import is_stt_available

            if not is_stt_available():
                await self._send(
                    chat_id,
                    "Voice note sunne ke liye faster-whisper install nahi hai "
                    "(pip install faster-whisper). Text mein likh do, wahi kaam.",
                )
                return
        except Exception:  # noqa: BLE001
            await self._send(chat_id, "Voice support nahi hai — text mein likho.")
            return

        # 2. Download
        file_info = await self._api("getFile", {"file_id": file_id})
        if not file_info or not file_info.get("ok"):
            await self._send(chat_id, "Voice download nahi hua, dobara bhejo.")
            return

        file_path = file_info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        tmp = None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=60.0) as dl:
                resp = await dl.get(url)
                resp.raise_for_status()

            tmp = tempfile.NamedTemporaryFile(
                suffix=".ogg", delete=False, dir=tempfile.gettempdir()
            )
            tmp.write(resp.content)
            tmp.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("Voice download fail: %s", exc)
            await self._send(chat_id, "Voice download nahi hua, dobara bhejo.")
            return

        # 3. Transcribe (Hinglish correction ke saath)
        try:
            text = await asyncio.to_thread(self._transcribe_ogg, Path(tmp.name))
        except Exception as exc:  # noqa: BLE001
            log.warning("Voice transcribe fail: %s", exc)
            text = ""

        try:
            os.unlink(tmp.name)
        except Exception:  # noqa: BLE001
            pass

        if not text:
            await self._send(chat_id, "Samajh nahi aaya — thoda saaf bolo ya likh do.")
            return

        await self._send(chat_id, f'🎙️ suna: "{text}"')
        reply = await self._run_agent(text)
        await self._send(chat_id, reply)

    def _transcribe_ogg(self, path: Path) -> str:
        """OGG voice note -> text (whisper + Hinglish correction)."""
        from faster_whisper import WhisperModel  # noqa: F401 — availability check

        from .voice.stt import WhisperConfig, WhisperSTT
        from .voice.hinglish_asr import correct_transcript

        cfg = WhisperConfig.from_env()
        stt = WhisperSTT(cfg)
        stt.load()

        result = stt.transcribe_file(path)
        corrected = correct_transcript(result.text)
        return corrected.corrected.strip()


# ======================================================================
#  Standalone run — python -m saarthi.telegram_bot
# ======================================================================


async def _main() -> None:
    from .agent import Agent

    agent = Agent()
    bot = TelegramBot(agent)
    started = await bot.start()
    if not started:
        print(
            "Telegram bot start nahi hua.\n"
            "  1. @BotFather se bot banao -> token\n"
            "  2. .env mein TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_CHAT_IDS daalo\n"
            "  (chat id: @userinfobot se milta hai)"
        )
        return

    print("Telegram bot chal raha hai — Ctrl+C se band karo.")
    try:
        while bot.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(_main())
