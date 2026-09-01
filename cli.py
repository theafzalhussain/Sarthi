#!/usr/bin/env python3
"""
SAARTHI CLI — terminal se agent se baat kar.

Chalane ke liye:
    python cli.py

Commands:
    /status      -> sab kuch ka status
    /models      -> kaunse LLM models available hain (LIVE check)
                    "model_not_found" error aaye to YE chala
    /tools       -> kaunse tools hain
    /skills      -> kaunsi skills seekhi hain
    /devices     -> connected devices + setup help
    /memory      -> yaad rakhi baatein
    /browser     -> browser kaise khulega (tab switch setting)
    /verbose     -> tool results dikhao/chhupao
    /reset       -> baat bhool jao (memory safe rahegi)
    /help        -> madad
    /quit        -> band karo

Look ka pura code `saarthi/ui.py` mein hai — yahan sirf logic hai.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import threading
from pathlib import Path

# Project root ko path mein daalo — taaki kahin se bhi chal jaaye
sys.path.insert(0, str(Path(__file__).resolve().parent))

from saarthi import __version__  # noqa: E402
from saarthi import line_input  # noqa: E402
from saarthi.agent import Agent  # noqa: E402
from saarthi.config import settings  # noqa: E402
from saarthi.image_input import (  # noqa: E402
    ImageInputError,
    from_file,
    from_screenshot,
)
from saarthi.tools.safety import format_confirmation, is_affirmative  # noqa: E402
from saarthi.ui import BRAND, ERR, MUTED, OK, TEXT, WARN, Ui  # noqa: E402

ui = Ui()

TAGLINE = "Personal AI Agent"


# ----------------------------------------------------------------------
#  Confirmation — risky kaam pe user se puchna
# ----------------------------------------------------------------------


async def ask_confirmation(action: str, details: dict) -> bool:
    """
    User se haan/nahi pucho.

    input() blocking hai — thread mein chalate hain taaki async
    loop na ruke.

    FAIL-SAFE: koi bhi gadbad (Ctrl+C, EOF, samajh na aaye) ho to
    NAHI. Chup-chaap kaam aage nahi badhta.
    """
    ui.blank()
    ui.hint(format_confirmation(action, details), title="confirmation required")

    prompt = "  " + ui.paint("approve? y / n", WARN, bold=True) + " " + ui.paint(
        ui.sym["prompt"], WARN
    ) + " "

    try:
        answer = await asyncio.to_thread(input, prompt)
    except (EOFError, KeyboardInterrupt):
        ui.error("Cancelled.")
        return False

    approved = is_affirmative(answer)
    if approved:
        ui.success("Approved — continuing.")
    else:
        ui.error("Denied — skipping this step.")
    ui.blank()
    return approved


# ----------------------------------------------------------------------
#  Thinking Spinner — user ko dikhao ki kaam ho raha hai
# ----------------------------------------------------------------------


class ThinkingSpinner:
    """
    Animated spinner jo tab tak chale jab tak pehla token na aaye.

    Jab user message bhejta hai, turant ye shuru hota hai.
    Pehla stream token aate hi band ho jaata hai.
    """

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _FRAMES_ASCII = ["|", "/", "-", "\\"]

    def __init__(self, label: str = "working"):
        self._label = label
        self._default_label = label
        self._running = False
        self._thread: threading.Thread | None = None
        self._use_unicode = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()
        self._frames = self._FRAMES if self._use_unicode else self._FRAMES_ASCII

    def start(self) -> None:
        """Spinner shuru karo."""
        if self._running:
            return
        # Har naye turn pe label reset — pichle model ka naam na dikhe
        self._label = self._default_label
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def set_label(self, label: str) -> None:
        """Chalte spinner ka label badlo (e.g. 'thinking (muse)')."""
        self._label = label

    def stop(self) -> None:
        """Spinner band karo aur line saaf karo."""
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        # Clear the spinner line
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _spin(self) -> None:
        """Background thread mein animation."""
        idx = 0
        while self._running:
            frame = self._frames[idx % len(self._frames)]
            sys.stdout.write(f"\r  \033[96m{frame}\033[0m  \033[90m{self._label}\033[0m")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.08)


# Global spinner instance
_spinner = ThinkingSpinner()


# ----------------------------------------------------------------------
#  Agent ka live output
# ----------------------------------------------------------------------


def make_output_handler(verbose: bool, state: dict | None = None):
    """Agent jo kar raha hai wo dikhao."""

    # Streaming state — track kare ki abhi stream chal raha hai
    streaming = {"active": False}

    def handle(kind: str, text: str) -> None:
        if not text:
            return

        if kind == "stream":
            # Pehla token aaya — spinner band karo
            _spinner.stop()

            # REAL-TIME streaming — token by token print karo
            if not streaming["active"]:
                streaming["active"] = True
                # Stream shuru — new line pe print shuru karo
                import sys
                sys.stdout.write("  ")
                sys.stdout.flush()
            import sys
            sys.stdout.write(text)
            sys.stdout.flush()
            # Mark that reply has been streamed (prevents duplicate in ui.reply)
            if state is not None:
                state['streamed_reply'] = True
        elif kind == "thinking":
            # Stream khatam hua tha to line break do
            if streaming["active"]:
                streaming["active"] = False
                import sys
                sys.stdout.write("\n")
                sys.stdout.flush()
            # Spinner already chal raha hai — extra line nahi chahiye
            # Just update the label if needed
        elif kind == "tool":
            _spinner.stop()
            if streaming["active"]:
                streaming["active"] = False
                import sys
                sys.stdout.write("\n")
                sys.stdout.flush()
            ui.activity("tool", text.strip())
        elif kind == "result":
            if streaming["active"]:
                streaming["active"] = False
                import sys
                sys.stdout.write("\n")
                sys.stdout.flush()
            if verbose:
                first = text.splitlines()[0] if text else ""
                ui.activity("result", first[:150])
        elif kind == "error":
            _spinner.stop()
            if streaming["active"]:
                streaming["active"] = False
                import sys
                sys.stdout.write("\n")
                sys.stdout.flush()
            first = text.splitlines()[0] if text else ""
            ui.activity("error", first[:200])
        elif kind == "debug":
            ui.activity("debug", text.strip())
        elif kind == "model":
            # Format: "provider|model" — spinner label update karo taaki
            # user ko dikhe kaunsa model abhi kaam kar raha hai.
            raw = text.strip()
            provider_name, _, model_name = raw.partition("|")
            provider_name = provider_name.strip() or "model"
            model_name = model_name.strip()

            # Sirf model naam spinner label mein — koi "thinking" word nahi.
            # e.g. spinner dikhega: "⠹  muse"
            _spinner.set_label(provider_name)

            # Same model bar-bar (multi-step loop) — visible line ek hi
            # baar dikhao, spam se bachao. Spinner label phir bhi update.
            last = state.get("last_model") if state is not None else None
            if raw != last:
                if state is not None:
                    state["last_model"] = raw
                # Streaming ke beech na aaye
                if not streaming["active"]:
                    label = provider_name
                    if model_name:
                        label += f"  \u00b7  {model_name}"
                    ui.activity("model", label)

    return handle


# ----------------------------------------------------------------------
#  Startup
# ----------------------------------------------------------------------


async def show_startup(agent: Agent) -> None:
    """Boot screen - compact, professional. Details are in /status."""
    # Compact one-shot status (provider summary + devices)
    status = await agent.devices.check_availability()
    ui.compact_status(agent.brain, status, agent.devices)

    # Disconnected devices - subtle one-liner
    disconnected = [
        name for name, device in agent.devices.devices.items()
        if not status.get(name, False)
    ]
    if disconnected:
        ui.muted(f"  Not connected: {', '.join(disconnected)}  \u00b7  /devices for setup")

    # Provider order warning (keep - it is important)
    if settings.order_is_explicit and settings.order_missing:
        ui.blank()
        ui.hint(
            "Your .env sets SAARTHI_PROVIDER_ORDER manually, and these\n"
            f"providers are missing from it: {', '.join(settings.order_missing)}\n"
            "They will be tried LAST, even if they are the strongest models.\n\n"
            "To get the best-first order, comment out (or delete) the\n"
            "SAARTHI_PROVIDER_ORDER line in .env and restart.",
            title="outdated provider order",
        )

    if settings.auto_approve:
        ui.hint(
            "Risky actions will run WITHOUT asking you first.\n"
            "Run /auto to turn off.",
            title="full access enabled",
        )

    ui.blank()
    ui.line(
        "  Ready  \u00b7  Ctrl+V/F2 = paste image  \u00b7  Esc = new chat  \u00b7  /help  \u00b7  any language",
        OK,
    )
    ui.blank()


# ----------------------------------------------------------------------
#  Slash commands
# ----------------------------------------------------------------------

COMMANDS = [
    ("/status", "brain, devices, memory and skills in one view"),
    ("/models", "list models available on your keys (live check)"),
    ("/tools", "all available tools"),
    ("/skills", "learned skills (Dikha Do Mode)"),
    ("/devices", "connected devices and setup instructions"),
    ("/memory", "everything the agent remembers about you"),
    ("/paste", "attach image from clipboard (or just press Ctrl+V / F2)"),
    ("/ss", "capture desktop screenshot and attach it"),
    ("/img <path>", "attach an image file"),
    ("/clearimg", "remove the attached image"),
    ("/browser", "how websites open — tab-safety setting"),
    ("/auto", "full access: run risky actions without asking"),
    ("/retry", "re-enable providers that were dropped"),
    ("/verbose", "show or hide intermediate tool results"),
    ("/reset", "clear the current conversation (memory is kept)"),
    ("/help", "show this help"),
    ("/quit", "exit"),
]

# Interface English mein hai, par examples DONO bhasha mein hain —
# user ko dikhna chahiye ki wo Hinglish mein bhi bol sakta hai.
EXAMPLES = [
    ("youtube pe tum hi ho gaana chala do", "Hinglish"),
    ("play Tere Bin on YouTube", "English"),
    ("mere phone me kya notifications hain", "Hinglish"),
    ("search for IRCTC tatkal booking time", "English"),
    ("yaad rakh ki mummy ka number 98765xxxxx hai", "Hinglish"),
    ("how much disk space is left on my laptop", "English"),
]


def show_help() -> None:
    """Help screen, grouped into sections."""
    ui.blank()
    ui.section("How to use")
    ui.muted(
        "Just type what you want in plain language. No syntax to remember."
    )
    ui.muted("Hinglish in, Hinglish out. English in, English out.")
    ui.blank()
    ui.table(
        ["example", "language"],
        [[f'"{text}"', lang] for text, lang in EXAMPLES],
    )
    ui.blank()

    ui.section("Dikha Do Mode — teach a new task")
    ui.table(
        ["say this", "what happens"],
        [
            ['"dekh, ye kaam yaad kar le"', "recording starts"],
            ["... then walk through the steps ...", "every step is remembered"],
            ['"isko bijli ka bill bol de"', "saved as a named skill"],
            ['"bijli ka bill bhar de"', "runs on its own next time"],
        ],
    )
    ui.muted(
        "  Skills self-heal: if the app's UI changes, the agent finds the "
        "new button and updates the skill."
    )
    ui.blank()

    ui.section("Commands")
    ui.table(["command", "description"], [[c, d] for c, d in COMMANDS])
    ui.blank()


def rank_model(model: str) -> int:
    """
    Model ko priority do — free aur sasta pehle.

    OpenRouter pe 300+ models hote hain, unme se kaam ke wahi hain
    jo free hain. Isliye ranking zaroori hai.
    """
    lowered = model.lower()
    if lowered.endswith(":free"):
        return 0  # bilkul free — sabse pehle
    if "gpt-oss" in lowered or "/free" in lowered:
        return 1  # Groq ke free models / free router
    if any(k in lowered for k in ("flash-lite", "instant", "mini", "gemma")):
        return 2  # chhote aur sasta
    if "flash" in lowered:
        return 3
    return 9


async def show_models(agent: Agent) -> None:
    """LIVE model discovery — deprecated model ka ilaaj."""
    ui.blank()
    ui.muted("Querying every provider — this takes a few seconds...")
    ui.blank()

    results = await agent.brain.discover_models()

    for provider_name, models in results.items():
        current = next(
            (p.model for p in agent.brain.providers if p.name == provider_name),
            "?",
        )
        ui.section(provider_name)

        if isinstance(models, str):
            ui.error(models)
            ui.blank()
            continue

        if not models:
            ui.error("No models returned.")
            ui.blank()
            continue

        ranked = sorted(models, key=lambda m: (rank_model(m), m))
        recommended = [m for m in ranked if rank_model(m) <= 2]
        others = [m for m in ranked if rank_model(m) > 2]

        rows = []
        for model in recommended[:15]:
            in_use = model == current
            rows.append(
                [
                    ui.badge(in_use),
                    model,
                    "currently in use" if in_use else "free / low cost",
                ]
            )

        # Current model recommended list mein na ho to bhi dikhao —
        # user ko pata hona chahiye abhi kya chal raha hai
        if current in others:
            rows.append([ui.badge(True), current, "currently in use"])

        if rows:
            ui.table(["", "model", "note"], rows)

        extra = []
        if len(recommended) > 15:
            extra.append(f"{len(recommended) - 15} more free models")
        if others:
            extra.append(f"{len(others)} other models (mostly paid)")
        if extra:
            ui.muted("  ... " + ", ".join(extra))

        ui.blank()

    ui.hint(
        "To switch models, set these in .env and restart:\n"
        "    DEEPSEEK_MODEL=...   NVIDIA_MODEL=...   MUSE_MODEL=...\n"
        "    GROQ_MODEL=...       GEMINI_MODEL=...   BLUESMINDS_MODEL=...",
        title="changing models",
    )


async def show_status(agent: Agent) -> None:
    """Sab kuch ek jagah."""
    ui.blank()
    ui.section("Brain")
    ui.brain_table(agent.brain)
    ui.blank()

    ui.section("Devices")
    status = await agent.devices.check_availability()
    ui.devices_table(agent.devices, status)
    ui.blank()

    memory_stats = await agent.memory.stats()
    skill_stats = await agent.skills.stats()

    ui.section("Agent")
    lang_note = {
        "auto": "auto — mirrors whatever language you write in",
        "hinglish": "hinglish (fixed)",
        "english": "english (fixed)",
        "hindi": "hindi (fixed)",
    }.get(settings.language, settings.language)

    rows = [
        ["tools", str(len(agent.tools))],
        ["memory", f"{memory_stats['facts']} facts, {memory_stats['messages']} messages"],
        [
            "skills",
            f"{skill_stats['skills']} learned "
            f"({skill_stats['steps']} steps, {skill_stats['total_runs']} runs)",
        ],
        ["reply language", lang_note],
        [
            "confirm risky actions",
            "on" if settings.confirm_risky else "OFF  <-- unsafe",
        ],
        [
            "full access (/auto)",
            "ON — runs without asking" if settings.auto_approve else "off",
        ],
        ["browser mode", settings.browser_mode],
        ["max steps per request", str(settings.max_steps)],
    ]
    if agent.recorder.recording:
        rows.append(
            ["dikha do mode", f"RECORDING ({agent.recorder.step_count} steps)"]
        )
    ui.table(["setting", "value"], rows)
    ui.blank()


async def show_devices(agent: Agent) -> None:
    """Devices + poora setup help."""
    ui.blank()
    agent.devices.invalidate_cache()  # phone plug/unplug hua ho to dobara check
    status = await agent.devices.check_availability()

    ui.section("Devices")
    hints = ui.devices_table(agent.devices, status, detailed=True)
    ui.blank()

    for name, hint in hints:
        ui.hint(hint, title=f"how to connect {name}")


def show_browser_info() -> None:
    """Browser kaise khulega — tab switch wali setting."""
    ui.blank()
    ui.section("Browser mode")

    modes = [
        [
            ui.badge(settings.browser_mode == "agent"),
            "agent",
            "SAARTHI uses its own window. Your tabs are never touched.",
        ],
        [
            ui.badge(settings.browser_mode == "system"),
            "system",
            "Your default browser, opened in a new tab without stealing focus.",
        ],
        [
            ui.badge(settings.browser_mode == "auto"),
            "auto",
            "Use the agent browser if Playwright is installed, else system.",
        ],
    ]
    ui.table(["", "mode", "behaviour"], modes)
    ui.blank()
    ui.hint(
        f"Current: SAARTHI_BROWSER_MODE={settings.browser_mode}\n"
        f"         SAARTHI_BROWSER_HEADLESS="
        f"{'true' if settings.browser_headless else 'false'}\n\n"
        "Change these in .env and restart.\n"
        "If your tabs still switch, use 'agent' mode.",
        title="current setting",
    )


async def handle_command(command: str, agent: Agent, state: dict) -> bool:
    """
    Slash command handle karo.

    Returns: chalte rehna hai? (False = quit)
    """
    cmd = command.strip().lower()

    if cmd in ("/quit", "/exit", "/q", "/bye"):
        ui.blank()
        ui.line("  Goodbye.", OK)
        ui.blank()
        return False

    if cmd in ("/help", "/h", "/madad"):
        show_help()
        return True

    if cmd == "/status":
        await show_status(agent)
        return True

    if cmd in ("/models", "/model"):
        await show_models(agent)
        return True

    if cmd == "/tools":
        ui.blank()
        ui.section(f"Tools ({len(agent.tools)})")
        ui.tools_table(agent.tools)
        ui.blank()
        return True

    if cmd == "/skills":
        ui.blank()
        skills = await agent.skills.list_skills()
        if not skills:
            ui.section("Skills")
            ui.muted("No skills learned yet.")
            ui.muted('To teach one, say: "dekh, ye kaam yaad kar le"')
        else:
            ui.section(f"Skills ({len(skills)})")
            ui.table(
                ["skill", "details"],
                [[s.name, s.summary()] for s in skills],
            )
        ui.blank()
        return True

    if cmd == "/devices":
        await show_devices(agent)
        return True

    if cmd in ("/browser", "/tab"):
        show_browser_info()
        return True

    if cmd in ("/auto", "/full"):
        settings.auto_approve = not settings.auto_approve
        if settings.auto_approve:
            ui.blank()
            ui.hint(
                "Risky actions will now run without asking:\n"
                "  shell commands, running skills, deleting memory\n\n"
                "These remain blocked no matter what:\n"
                "  OTP / PIN / password / CVV entry\n"
                "  rm -rf /, mkfs, fork bombs, curl | bash\n"
                "  pressing a final payment button\n\n"
                "These are hard blocks — no setting can bypass them.\n"
                "Run /auto again to turn full access off.",
                title="full access enabled",
            )
        else:
            ui.success("Full access disabled — you will be asked again.")
        return True

    if cmd in ("/retry", "/revive"):
        health = agent.brain.health()
        gone = [n for n, s in health.items() if s != "ok"]
        agent.brain.reset_health()
        if gone:
            ui.success(f"Re-enabled: {', '.join(gone)}")
        else:
            ui.muted("All providers are already healthy.")
        return True

    if cmd == "/memory":
        ui.blank()
        facts = await agent.memory.all_facts()
        if not facts:
            ui.section("Memory")
            ui.muted("Nothing remembered yet.")
        else:
            ui.section(f"Memory ({len(facts)})")
            ui.table(
                ["category", "key", "value"],
                [[f.category, f.key, f.value] for f in facts],
            )
        ui.blank()
        return True

    if cmd == "/verbose":
        state["verbose"] = not state["verbose"]
        agent.on_output = make_output_handler(state["verbose"], state)
        ui.muted(f"Verbose mode {'enabled' if state['verbose'] else 'disabled'}.")
        return True

    if cmd == "/reset":
        agent.reset_conversation()
        ui.muted("Conversation cleared. Saved memory and skills are untouched.")
        return True

    # --- Image attach commands ---
    # Ek image ko "pending" slot mein rakhte hain. Agla normal (non-slash)
    # message us image ke saath jaayega. Sabse aasaan tareeka: Ctrl+V ya
    # F2 seedha prompt par — par ye commands backup ke liye hain.
    if cmd in ("/paste", "/clip"):
        try:
            from saarthi.image_input import from_clipboard
            state["pending_image"] = from_clipboard()
            ui.success(
                "Image clipboard se attach ho gayi. Ab type kar ke bata "
                "agent ko kya karna hai."
            )
        except ImageInputError as exc:
            ui.error(str(exc))
        return True

    if cmd == "/ss":
        try:
            state["pending_image"] = from_screenshot()
            ui.success(
                "Desktop ka screenshot le liya aur attach kar diya. Ab bata "
                "kya karna hai."
            )
        except ImageInputError as exc:
            ui.error(str(exc))
        return True

    if cmd.startswith("/img"):
        raw = command.strip()[len("/img"):].strip()
        if not raw:
            ui.error("Path do: /img C:\\path\\to\\image.png")
            return True
        try:
            state["pending_image"] = from_file(raw)
            ui.success(
                "Image file attach ho gayi. Ab type kar ke bata agent ko "
                "kya karna hai."
            )
        except ImageInputError as exc:
            ui.error(str(exc))
        return True

    if cmd in ("/clearimg", "/noimg"):
        if state.get("pending_image"):
            state["pending_image"] = None
            ui.muted("Attached image hata di.")
        else:
            ui.muted("Koi image attach nahi thi.")
        return True

    ui.error(f"Unknown command '{command}'. Try /help")
    return True


# ----------------------------------------------------------------------
#  Main loop
# ----------------------------------------------------------------------


async def main() -> int:
    if settings.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s [%(name)s] %(message)s",
        )
    else:
        # Warnings ko stderr pe chhapne se roko.
        #
        # Python ka `logging.lastResort` handler har WARNING ko SEEDHA
        # stderr pe likh deta hai jab koi handler set na ho. Isse
        # "bluesminds fail hua: HTTP 400..." jaisi lines beech screen
        # mein aa jaati thi — bina rang, layout todti hui.
        #
        # Ye khabar ab UI se aati hai (agent -> brain.notify), isliye
        # logger ko chup kara rahe hain. NullHandler zaroori hai —
        # sirf level set karne se lastResort phir bhi chal jaata hai.
        saarthi_log = logging.getLogger("saarthi")
        saarthi_log.addHandler(logging.NullHandler())
        saarthi_log.setLevel(logging.ERROR)

    ui.banner(__version__, TAGLINE)

    state = {"verbose": True, "pending_image": None}

    agent = Agent(
        confirm=ask_confirmation,
        on_output=make_output_handler(state["verbose"], state),
    )

    # --- Brain ready hai? ---
    if not agent.brain.is_ready:
        ui.hint(settings.setup_help(), title="setup required")
        return 1

    await show_startup(agent)
    await agent.start_session()

    prompt = ui.prompt("you")

    # Ctrl+V se seedha image paste ke liye custom reader (Windows).
    # Non-Windows par normal input().
    use_paste_reader = line_input.supported()

    # --- REPL ---
    while True:
        pasted_image: str | None = None
        try:
            if use_paste_reader:
                user_input, pasted_image = await asyncio.to_thread(
                    line_input.read_line, prompt
                )
            else:
                user_input = await asyncio.to_thread(input, prompt)
        except line_input.EscPressed:
            # Khaali prompt par Esc — poori baat bhool ke naya chat
            ui.blank()
            agent.reset_conversation()
            try:
                await agent.start_session()
            except Exception:  # noqa: BLE001
                pass
            state["pending_image"] = None
            continue
        except (EOFError, KeyboardInterrupt):
            ui.blank(2)
            ui.line("  Goodbye.", OK)
            ui.blank()
            break

        user_input = user_input.strip()

        # Ctrl+V (ya F2) se image paste hui? To pending slot mein rakho.
        if pasted_image:
            state["pending_image"] = pasted_image
            if not user_input:
                ui.success(
                    "  Image paste ho gayi. Ab type kar ke bata kya karna "
                    "hai, phir Enter."
                )
                continue

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not await handle_command(user_input, agent, state):
                break
            continue

        # --- Agent ko kaam do ---
        state["streamed_reply"] = False
        state["last_model"] = None

        # Image attach hui thi (Ctrl+V/F2/command)? Is message ke saath
        # bhejo, phir hata do.
        attached_image = state.get("pending_image")
        if attached_image:
            ui.muted("  (attached image is being sent with your message)")

        _spinner.start()
        started = time.monotonic()

        # Esc-to-cancel: run_turn ko task mein chalao, background mein
        # Esc suno. Esc dabe to turn cancel ho jaaye.
        turn_task = asyncio.ensure_future(
            agent.run_turn(user_input, image_b64=attached_image)
        )
        esc_stop = threading.Event()
        esc_task = None

        async def _esc_watcher() -> None:
            pressed = await asyncio.to_thread(line_input.poll_for_esc, esc_stop)
            if pressed and not turn_task.done():
                turn_task.cancel()

        def _esc_stop_set() -> None:
            esc_stop.set()
            if esc_task is not None:
                esc_task.cancel()

        if line_input.supported():
            esc_task = asyncio.ensure_future(_esc_watcher())

        try:
            result = await turn_task
        except (asyncio.CancelledError, KeyboardInterrupt):
            _spinner.stop()
            ui.blank()
            ui.error("Cancellation")
            ui.blank()
            agent.reset_conversation()
            try:
                await agent.start_session()
            except Exception:  # noqa: BLE001
                pass
            _esc_stop_set()
            state["pending_image"] = None
            continue
        except Exception as exc:  # noqa: BLE001 — CLI kabhi crash na ho
            _spinner.stop()
            ui.blank()
            ui.reply_error(f"Something went wrong: {exc}")
            ui.blank()
            if settings.debug:
                import traceback

                traceback.print_exc()
            _esc_stop_set()
            state["pending_image"] = None
            continue
        finally:
            # Esc-watcher band karo; image ek hi baar bhejni thi
            _esc_stop_set()
            if attached_image:
                state["pending_image"] = None

        _spinner.stop()

        elapsed = time.monotonic() - started

        ui.blank()
        if result.error:
            ui.reply_error(result.error)
        else:
            # Meta line — compact, professional
            meta = ""
            if state["verbose"]:
                parts = []
                if result.tool_calls:
                    parts.append(", ".join(result.tool_calls))
                parts.append(f"{elapsed:.1f}s")
                meta = "  ·  ".join(parts)
            # Agar reply streaming se already print ho chuka to skip
            if state.get("streamed_reply"):
                if meta:
                    ui.muted(meta)
                state["streamed_reply"] = False
            else:
                ui.reply(result.reply, meta=meta)

        # Free tier ke tokens bachao — purani baat trim karo
        agent.trim_history()
        ui.blank()

    return 0


def _run_login() -> int:
    """
    Save API keys to the device-wide config (~/.saarthi/.env), so `saarthi`
    works from ANY folder without a local .env — like `kiro`.

    This asks for keys interactively and writes them once per device.
    Existing keys are kept unless you enter a new value.
    """
    from saarthi.config import GLOBAL_CONFIG_DIR, GLOBAL_ENV_FILE

    ui.blank()
    ui.section("SAARTHI — device login")
    ui.muted(
        "Keys are saved to your home folder (not this project), so you only "
        "do this ONCE per device. After that, `saarthi` runs from any folder."
    )
    ui.muted(f"  File: {GLOBAL_ENV_FILE}")
    ui.blank()
    ui.muted("Press Enter to skip any key you don't have. All are free:")
    ui.muted("  NVIDIA (1 key = 4 models): https://build.nvidia.com")
    ui.muted("  Gemini (for screenshots):  https://aistudio.google.com/apikey")
    ui.muted("  Groq (fast):               https://console.groq.com")
    ui.blank()

    # Which keys we ask for. Add more here if needed.
    key_prompts = [
        ("NVIDIA_API_KEY", "NVIDIA key (nvapi-...)"),
        ("GEMINI_API_KEY", "Gemini key"),
        ("GROQ_API_KEY", "Groq key"),
        ("OPENROUTER_API_KEY", "OpenRouter key (optional)"),
        ("BLUESMINDS_API_KEY", "Bluesminds key (optional)"),
    ]

    # Read existing values so we don't wipe keys the user already saved.
    existing: dict[str, str] = {}
    if GLOBAL_ENV_FILE.exists():
        for line in GLOBAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    collected = dict(existing)
    entered_any = False
    for env_key, label in key_prompts:
        have = " (saved)" if existing.get(env_key) else ""
        try:
            value = input(f"  {label}{have}: ").strip()
        except (EOFError, KeyboardInterrupt):
            ui.blank()
            ui.error("Cancelled.")
            return 1
        if value:
            collected[env_key] = value
            entered_any = True

    # Keep only non-empty keys
    collected = {k: v for k, v in collected.items() if v}

    if not collected:
        ui.blank()
        ui.error("No keys entered and none saved before — nothing to write.")
        return 1

    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SAARTHI device-wide keys — created by `saarthi login`.",
        "# This file is NOT in Git. It lets `saarthi` run from any folder.",
        "",
    ]
    lines += [f"{k}={v}" for k, v in collected.items()]
    GLOBAL_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Best-effort: lock down permissions on POSIX (owner read/write only).
    try:
        import os as _os
        import stat as _stat

        if hasattr(_os, "chmod"):
            _os.chmod(GLOBAL_ENV_FILE, _stat.S_IRUSR | _stat.S_IWUSR)
    except Exception:  # noqa: BLE001
        pass

    ui.blank()
    ui.success(f"Saved {len(collected)} key(s) to {GLOBAL_ENV_FILE}")
    ui.muted("Now run `saarthi` from any folder — no local .env needed.")
    ui.blank()
    return 0


def run() -> None:
    """
    Synchronous entry point for the `saarthi` command.

    This is what `pyproject.toml`'s [project.scripts] calls, so `saarthi`
    works as a global command from any folder on any device (like `kiro`).

    Subcommands:
        saarthi            -> start the agent
        saarthi login      -> save API keys to the device (once per device)
        saarthi setup      -> alias for login
    """
    args = sys.argv[1:]
    if args and args[0] in ("login", "setup", "auth", "key", "keys"):
        try:
            sys.exit(_run_login())
        except KeyboardInterrupt:
            sys.exit(0)

    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    run()
