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

TAGLINE = "Hinglish-first personal AI agent"


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
    ui.hint(format_confirmation(action, details), title="confirm karna hai")

    prompt = "  " + ui.paint("haan / nahi", WARN, bold=True) + " " + ui.paint(
        ui.sym["prompt"], WARN
    ) + " "

    try:
        answer = await asyncio.to_thread(input, prompt)
    except (EOFError, KeyboardInterrupt):
        ui.error("cancel kar diya")
        return False

    approved = is_affirmative(answer)
    if approved:
        ui.success("theek hai, kar raha hun")
    else:
        ui.error("nahi kar raha")
    ui.blank()
    return approved


# ----------------------------------------------------------------------
#  Agent ka live output
# ----------------------------------------------------------------------


def make_output_handler(verbose: bool):
    """Agent jo kar raha hai wo dikhao."""

    def handle(kind: str, text: str) -> None:
        if not text:
            return

        if kind == "thinking":
            ui.activity("thinking", text.strip())
        elif kind == "tool":
            ui.activity("tool", text.strip())
        elif kind == "result":
            if verbose:
                first = text.splitlines()[0] if text else ""
                ui.activity("result", first[:150])
        elif kind == "error":
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
        ui.muted(f"{missing} abhi connected nahi — setup ke liye /devices")

    if not agent.brain.has_vision:
        ui.muted("Vision provider nahi — screenshot nahi dekh paunga (/models)")

    ui.blank()
    ui.line(
        f"  Ready hun bhai. Bol kya karna hai.   {ui.sym['bullet']}   /help se madad",
        OK,
    )
    ui.blank()


# ----------------------------------------------------------------------
#  Slash commands
# ----------------------------------------------------------------------

COMMANDS = [
    ("/status", "brain, devices, memory, skills — sab ek jagah"),
    ("/models", "kaunse LLM models available hain (LIVE check)"),
    ("/tools", "saare tools ki list"),
    ("/skills", "seekhi hui skills (Dikha Do Mode)"),
    ("/devices", "connected devices + setup instructions"),
    ("/memory", "yaad rakhi hui baatein"),
    ("/browser", "browser kaise khulega — tab switch setting"),
    ("/verbose", "tool results dikhao ya chhupao"),
    ("/reset", "current baat bhool jao (memory safe rahegi)"),
    ("/help", "ye madad"),
    ("/quit", "band karo"),
]

EXAMPLES = [
    "youtube pe tum hi ho gaana chala do",
    "mere phone me kya notifications hain",
    "internet pe dhoondh IRCTC tatkal ka time",
    "yaad rakh ki mummy ka number 98765xxxxx hai",
    "laptop pe batao kitni disk space bachi hai",
]


def show_help() -> None:
    """Madad — sections mein baanti hui."""
    ui.blank()
    ui.section("Kaise use kare")
    ui.muted("Bas normal Hinglish mein bol. Koi syntax yaad karne ki zarurat nahi.")
    ui.blank()
    for example in EXAMPLES:
        ui.line(f'    {ui.sym["arrow"]}  "{example}"', TEXT)
    ui.blank()

    ui.section("Dikha Do Mode — naya kaam sikhana")
    ui.table(
        ["bol", "kya hoga"],
        [
            ['"dekh, ye kaam yaad kar le"', "recording ON"],
            ["... phir steps batao ...", "agent har step yaad karta hai"],
            ['"isko bijli ka bill bol de"', "skill save ho gayi"],
            ['"bijli ka bill bhar de"', "agli baar khud ho jaayega"],
        ],
    )
    ui.blank()

    ui.section("Commands")
    ui.table(["command", "kaam"], [[c, d] for c, d in COMMANDS])
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
    ui.muted("Har provider se live pata kar raha hun (thoda time lagega)...")
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
            ui.error("koi model nahi mila")
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
                    "abhi yahi use ho raha" if in_use else "free / sasta",
                ]
            )

        # Current model recommended list mein na ho to bhi dikhao —
        # user ko pata hona chahiye abhi kya chal raha hai
        if current in others:
            rows.append([ui.badge(True), current, "abhi yahi use ho raha"])

        if rows:
            ui.table(["", "model", "note"], rows)

        extra = []
        if len(recommended) > 15:
            extra.append(f"{len(recommended) - 15} aur free models")
        if others:
            extra.append(f"{len(others)} baaki models (zyadatar paid)")
        if extra:
            ui.muted("  ... " + ", ".join(extra))

        ui.blank()

    ui.hint(
        "Model badalna hai? .env mein set kar, phir SAARTHI restart kar:\n"
        "    GROQ_MODEL=...      NVIDIA_MODEL=...\n"
        "    GEMINI_MODEL=...    BLUESMINDS_MODEL=...",
        title="model kaise badle",
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
    rows = [
        ["tools", str(len(agent.tools))],
        ["memory", f"{memory_stats['facts']} facts, {memory_stats['messages']} messages"],
        [
            "skills",
            f"{skill_stats['skills']} seekhi "
            f"({skill_stats['steps']} steps, {skill_stats['total_runs']} baar chali)",
        ],
        ["language", settings.language],
        [
            "risky confirmation",
            "ON" if settings.confirm_risky else "OFF  <-- khatarnak!",
        ],
        ["browser mode", settings.browser_mode],
        ["max steps", str(settings.max_steps)],
    ]
    if agent.recorder.recording:
        rows.append(
            ["dikha do mode", f"ON ({agent.recorder.step_count} steps record hue)"]
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
        ui.hint(hint, title=f"{name} connect kaise kare")


def show_browser_info() -> None:
    """Browser kaise khulega — tab switch wali setting."""
    ui.blank()
    ui.section("Browser mode")

    modes = [
        [
            ui.badge(settings.browser_mode == "agent"),
            "agent",
            "SAARTHI ki apni alag window. Tere tabs kabhi nahi badlenge.",
        ],
        [
            ui.badge(settings.browser_mode == "system"),
            "system",
            "Tera normal browser. Naye tab mein khulega (focus nahi chheenta).",
        ],
        [
            ui.badge(settings.browser_mode == "auto"),
            "auto",
            "Playwright ho to agent, warna system.",
        ],
    ]
    ui.table(["", "mode", "matlab"], modes)
    ui.blank()
    ui.hint(
        f"Abhi: SAARTHI_BROWSER_MODE={settings.browser_mode}\n"
        f"      SAARTHI_BROWSER_HEADLESS="
        f"{'true' if settings.browser_headless else 'false'}\n\n"
        "Badalna hai to .env mein set kar aur restart kar.\n"
        "Tera tab switch ho raha hai? 'agent' mode use kar.",
        title="setting",
    )


async def handle_command(command: str, agent: Agent, state: dict) -> bool:
    """
    Slash command handle karo.

    Returns: chalte rehna hai? (False = quit)
    """
    cmd = command.strip().lower()

    if cmd in ("/quit", "/exit", "/q", "/bye"):
        ui.blank()
        ui.line("  Chalo bye! Phir milte hain.", OK)
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
            ui.muted("Abhi koi skill nahi seekhi.")
            ui.muted('Sikhane ke liye bol: "dekh, ye kaam yaad kar le"')
        else:
            ui.section(f"Skills ({len(skills)})")
            ui.table(
                ["skill", "detail"],
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

    if cmd == "/memory":
        ui.blank()
        facts = await agent.memory.all_facts()
        if not facts:
            ui.section("Memory")
            ui.muted("Abhi kuch yaad nahi hai.")
        else:
            ui.section(f"Memory ({len(facts)})")
            ui.table(
                ["category", "kya", "value"],
                [[f.category, f.key, f.value] for f in facts],
            )
        ui.blank()
        return True

    if cmd == "/verbose":
        state["verbose"] = not state["verbose"]
        agent.on_output = make_output_handler(state["verbose"])
        ui.muted(f"Verbose mode: {'ON' if state['verbose'] else 'OFF'}")
        return True

    if cmd == "/reset":
        agent.reset_conversation()
        ui.muted("Baat reset kar di. Memory aur skills safe hain.")
        return True

    ui.error(f"'{command}' samajh nahi aaya. /help try kar.")
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

    ui.banner(__version__, TAGLINE)

    state = {"verbose": True}

    agent = Agent(
        confirm=ask_confirmation,
        on_output=make_output_handler(state["verbose"]),
    )

    # --- Brain ready hai? ---
    if not agent.brain.is_ready:
        ui.hint(settings.setup_help(), title="ruk ja — pehle setup")
        return 1

    await show_startup(agent)
    await agent.start_session()

    prompt = ui.prompt("tu")

    # --- REPL ---
    while True:
        try:
            user_input = await asyncio.to_thread(input, prompt)
        except (EOFError, KeyboardInterrupt):
            ui.blank(2)
            ui.line("  Chalo bye!", OK)
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
        started = time.monotonic()
        try:
            result = await agent.run_turn(user_input)
        except KeyboardInterrupt:
            ui.blank()
            ui.error("rok diya")
            ui.blank()
            continue
        except Exception as exc:  # noqa: BLE001 — CLI kabhi crash na ho
            ui.blank()
            ui.reply_error(f"Kuch gadbad ho gayi: {exc}")
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
