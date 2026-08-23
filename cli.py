#!/usr/bin/env python3
"""
SAARTHI CLI — terminal se agent se baat kar.

Chalane ke liye:
    python cli.py

Commands:
    /status      -> sab kuch ka status
    /tools       -> kaunse tools hain
    /skills      -> kaunsi skills seekhi hain
    /devices     -> connected devices
    /memory      -> yaad rakhi baatein
    /reset       -> baat bhool jao (memory safe rahegi)
    /help        -> madad
    /quit        -> band karo
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Project root ko path mein daalo — taaki kahin se bhi chal jaaye
sys.path.insert(0, str(Path(__file__).resolve().parent))

from saarthi import __version__  # noqa: E402
from saarthi.agent import Agent  # noqa: E402
from saarthi.config import settings  # noqa: E402
from saarthi.tools.safety import format_confirmation, is_affirmative  # noqa: E402

# ----------------------------------------------------------------------
#  Terminal colors — rich ho to accha, na ho to plain
# ----------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.markdown import Markdown

    console: Console | None = Console()
except ImportError:
    console = None
    Markdown = None  # type: ignore[assignment]


COLORS = {
    "user": "\033[96m",       # cyan
    "agent": "\033[92m",      # green
    "tool": "\033[93m",       # yellow
    "error": "\033[91m",      # red
    "dim": "\033[90m",        # gray
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def paint(text: str, color: str) -> str:
    """Text ko rang do."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def show(text: str, color: str = "reset") -> None:
    print(paint(text, color))


BANNER = r"""
   ____    _        _    ____ _____ _   _ ___
  / ___|  / \      / \  |  _ \_   _| | | |_ _|
  \___ \ / _ \    / _ \ | |_) || | | |_| || |
   ___) / ___ \  / ___ \|  _ < | | |  _  || |
  |____/_/   \_\/_/   \_\_| \_\|_| |_| |_|___|

  Tera apna AI agent — Hinglish samajhta hai
"""


# ----------------------------------------------------------------------
#  Confirmation — risky kaam pe user se puchna
# ----------------------------------------------------------------------


async def ask_confirmation(action: str, details: dict) -> bool:
    """
    User se haan/nahi pucho.

    input() blocking hai — thread mein chalate hain taaki async
    loop na ruke.
    """
    show(format_confirmation(action, details), "tool")

    try:
        answer = await asyncio.to_thread(input, paint("  > ", "bold"))
    except (EOFError, KeyboardInterrupt):
        show("  (cancel kar diya)", "dim")
        return False

    approved = is_affirmative(answer)
    show(
        "  -> theek hai, kar raha hun" if approved else "  -> nahi kar raha",
        "dim" if approved else "error",
    )
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
            show(f"  ...{text}", "dim")
        elif kind == "tool":
            show(f"  [chal raha hai] {text}", "tool")
        elif kind == "result":
            if verbose:
                first = text.splitlines()[0] if text else ""
                show(f"  [result] {first[:160]}", "dim")
        elif kind == "error":
            first = text.splitlines()[0] if text else ""
            show(f"  [fail] {first[:200]}", "error")
        elif kind == "debug":
            show(f"  {text}", "dim")

    return handle


# ----------------------------------------------------------------------
#  Slash commands
# ----------------------------------------------------------------------

HELP_TEXT = """
SAARTHI — kaise use kare

Bas normal Hinglish mein bol:
    "paytm kholo"
    "mere phone me kya notifications hain"
    "internet pe dhoondh ki IRCTC tatkal ka time kya hai"
    "yaad rakh ki mummy ka number 98765xxxxx hai"
    "laptop pe batao kitni disk space bachi hai"

DIKHA DO MODE (naya kaam sikhana):
    "dekh, ye kaam yaad kar le"     -> recording ON
    ... phir batao kya karna hai ...
    "isko bijli ka bill bol de"     -> skill save
    Agli baar: "bijli ka bill bhar de"  -> khud ho jaayega

Commands:
    /status    sab kuch ka status
    /tools     saare tools ki list
    /skills    seekhi hui skills
    /devices   connected devices
    /memory    yaad rakhi baatein
    /verbose   tool results dikhao/chhupao
    /reset     current baat bhool jao
    /help      ye madad
    /quit      band karo
"""


async def handle_command(command: str, agent: Agent, state: dict) -> bool:
    """
    Slash command handle karo.

    Returns: chalte rehna hai? (False = quit)
    """
    cmd = command.strip().lower()

    if cmd in ("/quit", "/exit", "/q", "/bye"):
        show("\n  Chalo bye! Phir milte hain. \n", "agent")
        return False

    if cmd in ("/help", "/h", "/madad"):
        show(HELP_TEXT, "dim")
        return True

    if cmd == "/status":
        show("")
        show(await agent.status(), "dim")
        show("")
        return True

    if cmd == "/tools":
        show(f"\n  {len(agent.tools)} tools available:\n", "bold")
        show(agent.tools.describe(), "dim")
        show("")
        return True

    if cmd == "/skills":
        skills = await agent.skills.list_skills()
        if not skills:
            show(
                "\n  Abhi koi skill nahi seekhi.\n"
                "  Sikhane ke liye bol: 'dekh, ye kaam yaad kar le'\n",
                "dim",
            )
        else:
            show(f"\n  {len(skills)} skills seekhi hui hain:\n", "bold")
            for skill in skills:
                show(f"  - {skill.summary()}", "dim")
            show("")
        return True

    if cmd == "/devices":
        show("")
        agent.devices.invalidate_cache()  # dobara check karo
        show(await agent.devices.describe(), "dim")
        show("")
        return True

    if cmd == "/memory":
        facts = await agent.memory.all_facts()
        if not facts:
            show("\n  Abhi kuch yaad nahi hai.\n", "dim")
        else:
            show(f"\n  {len(facts)} baatein yaad hain:\n", "bold")
            for fact in facts:
                show(f"  - [{fact.category}] {fact.key}: {fact.value}", "dim")
            show("")
        return True

    if cmd == "/verbose":
        state["verbose"] = not state["verbose"]
        agent.on_output = make_output_handler(state["verbose"])
        show(
            f"  Verbose mode: {'ON' if state['verbose'] else 'OFF'}",
            "dim",
        )
        return True

    if cmd == "/reset":
        agent.reset_conversation()
        show("  Baat reset kar di. Memory aur skills safe hain.", "dim")
        return True

    show(f"  '{command}' samajh nahi aaya. /help try kar.", "error")
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

    show(BANNER, "agent")
    show(f"  v{__version__}", "dim")

    state = {"verbose": True}

    agent = Agent(
        confirm=ask_confirmation,
        on_output=make_output_handler(state["verbose"]),
    )

    # --- Brain ready hai? ---
    if not agent.brain.is_ready:
        show("\n  RUK JA — pehle setup karna padega:\n", "error")
        show(settings.setup_help(), "dim")
        show("")
        return 1

    show("\n  Brain:", "bold")
    show(agent.brain.status(), "dim")

    # --- Devices ---
    show("\n  Devices:", "bold")
    show(await agent.devices.describe(), "dim")

    if not agent.brain.has_vision:
        show(
            "\n  Dhyan: Gemini key nahi hai, isliye screenshot nahi dekh "
            "paunga.\n  Free key: https://aistudio.google.com/apikey",
            "tool",
        )

    show("\n  Ready hun bhai. Bol kya karna hai. (/help se madad)\n", "agent")

    await agent.start_session()

    # --- REPL ---
    while True:
        try:
            user_input = await asyncio.to_thread(input, paint("  tu > ", "user"))
        except (EOFError, KeyboardInterrupt):
            show("\n\n  Chalo bye!\n", "agent")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            if not await handle_command(user_input, agent, state):
                break
            continue

        # --- Agent ko kaam do ---
        try:
            result = await agent.run_turn(user_input)
        except KeyboardInterrupt:
            show("\n  (rok diya)\n", "error")
            continue
        except Exception as exc:  # noqa: BLE001 — CLI kabhi crash na ho
            show(f"\n  Kuch gadbad ho gayi: {exc}\n", "error")
            if settings.debug:
                import traceback

                traceback.print_exc()
            continue

        show("")
        if result.error:
            show(f"  saarthi > {result.error}", "error")
        else:
            if console and Markdown:
                print(paint("  saarthi > ", "agent"), end="")
                console.print(Markdown(result.reply))
            else:
                show(f"  saarthi > {result.reply}", "agent")

        if state["verbose"] and result.tool_calls:
            show(
                f"  ({result.steps_used} steps, tools: "
                f"{', '.join(result.tool_calls)})",
                "dim",
            )

        # Free tier ke tokens bachao — purani baat trim karo
        agent.trim_history()
        show("")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
