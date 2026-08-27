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
from pathlib import Path

# Project root ko path mein daalo — taaki kahin se bhi chal jaaye
sys.path.insert(0, str(Path(__file__).resolve().parent))

from saarthi import __version__  # noqa: E402
from saarthi.agent import Agent  # noqa: E402
from saarthi.config import settings  # noqa: E402
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
            ui.activity("thinking", text.strip())
        elif kind == "tool":
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
            if streaming["active"]:
                streaming["active"] = False
                import sys
                sys.stdout.write("\n")
                sys.stdout.flush()
            first = text.splitlines()[0] if text else ""
            ui.activity("error", first[:200])
        elif kind == "debug":
            ui.activity("debug", text.strip())

    return handle


# ----------------------------------------------------------------------
#  Startup
# ----------------------------------------------------------------------


async def show_startup(agent: Agent) -> None:
    """Boot screen — brain, devices, aur kya missing hai."""
    ui.section("Brain")
    ui.brain_table(agent.brain)
    ui.blank()

    ui.section("Devices")
    status = await agent.devices.check_availability()
    hints = ui.devices_table(agent.devices, status)
    ui.blank()

    # Kya missing hai — ek compact line. Detail /devices pe milegi,
    # startup pe screen bharna nahi chahiye.
    if hints:
        missing = ", ".join(name for name, _ in hints)
        ui.muted(f"Not connected: {missing}  —  run /devices for setup steps")

    if not agent.brain.has_vision:
        ui.muted("No vision provider — screenshots cannot be analysed (/models)")

    # Multi-phone detected — tell user
    if agent.devices._multi_phone_serials:
        serials = agent.devices._multi_phone_serials
        ui.blank()
        ui.hint(
            f"{len(serials)} phones detected:\n"
            + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(serials))
            + f"\n\nDefault: {serials[0]}\n"
            "To pin a specific phone, set in .env:\n"
            f"  SAARTHI_ANDROID_SERIAL={serials[0]}",
            title="multiple phones",
        )

    # .env mein purana provider order pada hai?
    #
    # Ye ek chup-chaap trap hai: user ne pehle order likha tha, baad mein
    # naye (smarter) models add hue — wo automatically SABSE AAKHIR chale
    # gaye. User ko lagta hai naya model use ho raha hai, par nahi ho raha.
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
            "Risky actions will run WITHOUT asking you first.\n\n"
            "Hard blocks still apply and cannot be bypassed:\n"
            "  OTP / PIN / password / CVV entry\n"
            "  rm -rf /, mkfs, fork bombs, curl | bash\n"
            "  pressing a final payment button\n\n"
            "Turn it off with /auto",
            title="full access enabled",
        )

    ui.blank()
    ui.line(
        f"  Ready.   {ui.sym['bullet']}   Streaming"
        f"   {ui.sym['bullet']}   Type in any language"
        f"   {ui.sym['bullet']}   /help",
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

    state = {"verbose": True}

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

    # --- REPL ---
    while True:
        try:
            user_input = await asyncio.to_thread(input, prompt)
        except (EOFError, KeyboardInterrupt):
            ui.blank(2)
            ui.line("  Goodbye.", OK)
            ui.blank()
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            if not await handle_command(user_input, agent, state):
                break
            continue

        # --- Agent ko kaam do ---
        state["streamed_reply"] = False
        started = time.monotonic()
        try:
            result = await agent.run_turn(user_input)
        except KeyboardInterrupt:
            ui.blank()
            ui.error("Interrupted.")
            ui.blank()
            continue
        except Exception as exc:  # noqa: BLE001 — CLI kabhi crash na ho
            ui.blank()
            ui.reply_error(f"Something went wrong: {exc}")
            ui.blank()
            if settings.debug:
                import traceback

                traceback.print_exc()
            continue

        elapsed = time.monotonic() - started

        ui.blank()
        if result.error:
            ui.reply_error(result.error)
        else:
            # Meta line — kitna kaam laga. Debugging mein bahut kaam aata hai.
            meta = ""
            if state["verbose"]:
                bits = [f"{result.steps_used} steps", f"{elapsed:.1f}s"]
                if result.tool_calls:
                    bits.insert(1, ", ".join(result.tool_calls))
                meta = f"  {ui.sym['bullet']}  ".join(bits)
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


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
