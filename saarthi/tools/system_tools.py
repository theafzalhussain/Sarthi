"""
System Tools — basic utilities.

Chhote tools, par bahut kaam ke. Time/date wala tool specially —
LLM ko current time nahi pata hota, wo hamesha guess karta hai.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..devices.base import ActionResult
from .base import Tool, ToolContext

# India Standard Time — SAARTHI Indian users ke liye hai
IST = timezone(timedelta(hours=5, minutes=30))

HINDI_DAYS = {
    0: "Somvaar (Monday)",
    1: "Mangalvaar (Tuesday)",
    2: "Budhvaar (Wednesday)",
    3: "Guruvaar (Thursday)",
    4: "Shukravaar (Friday)",
    5: "Shanivaar (Saturday)",
    6: "Ravivaar (Sunday)",
}


class TimeTool(Tool):
    name = "time_bata"
    description = (
        "Report the current time and date (India time). Use this whenever "
        "date/time is involved — you do not know the current time on your own."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        now = datetime.now(IST)

        # Din ka hissa — natural Hinglish jawab ke liye
        hour = now.hour
        if hour < 5:
            part = "raat"
        elif hour < 12:
            part = "subah"
        elif hour < 17:
            part = "dopahar"
        elif hour < 20:
            part = "shaam"
        else:
            part = "raat"

        return ActionResult.success(
            f"Time: {now.strftime('%I:%M %p')} ({part})\n"
            f"Date: {now.strftime('%d %B %Y')}\n"
            f"Din: {HINDI_DAYS[now.weekday()]}\n"
            f"Timezone: IST",
            iso=now.isoformat(),
            hour=hour,
        )


class CalculateTool(Tool):
    name = "calculate_karo"
    description = (
        "Do a maths calculation. Simple arithmetic: +, -, *, /, **, %, "
        "brackets. Example: '2500 * 12 + 300'"
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A maths expression, e.g. '2500*12'",
            }
        },
        "required": ["expression"],
    }

    async def run(self, ctx: ToolContext, expression: str) -> ActionResult:
        # SAFETY: eval khatarnak hai. Sirf safe characters allow karo
        # aur koi naam/function allow nahi — sirf numbers aur operators.
        allowed = set("0123456789+-*/%().eE ")
        if not set(expression) <= allowed:
            bad = "".join(sorted(set(expression) - allowed))
            return ActionResult.failure(
                f"Sirf numbers aur + - * / % ( ) chalega. "
                f"Ye characters allowed nahi: {bad}"
            )

        # ** allow hai par bahut bade power se bachao (memory bomb)
        if "**" in expression:
            try:
                base, _, exponent = expression.partition("**")
                if float(exponent.strip(" ()")) > 100:
                    return ActionResult.failure("Power bahut bada hai, 100 tak hi")
            except ValueError:
                pass

        try:
            # Builtins band — sirf pure arithmetic
            result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        except ZeroDivisionError:
            return ActionResult.failure("Zero se divide nahi kar sakte")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Calculation galat hai: {exc}")

        if isinstance(result, float) and result.is_integer():
            result = int(result)

        return ActionResult.success(f"{expression} = {result}", value=result)


class AskUserTool(Tool):
    name = "user_se_pucho"
    description = (
        "Ask the user a question when something is unclear. Asking is "
        "better than guessing. Examples: who to message, which option to "
        "choose."
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "What to ask (in the user's language)",
            }
        },
        "required": ["question"],
    }

    async def run(self, ctx: ToolContext, question: str) -> ActionResult:
        # Agent loop isko dekh ke user se puchega
        ctx.scratch["pending_question"] = question
        return ActionResult.success(
            f"User se poocha: {question}",
            needs_user_input=True,
            question=question,
        )


def system_tools() -> list[Tool]:
    """Saare system tools."""
    return [
        TimeTool(),
        CalculateTool(),
        AskUserTool(),
    ]
