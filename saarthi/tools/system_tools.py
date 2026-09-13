"""
System Tools — basic utilities + advanced Jarvis OS capabilities.
Provides live system status (CPU, RAM, Battery, Disk), Volume & Media controls,
App management, Screen Vision, Reminders, Time, and Calculator.
"""

from __future__ import annotations

import asyncio
import base64
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
        allowed = set("0123456789+-*/%().eE ")
        if not set(expression) <= allowed:
            bad = "".join(sorted(set(expression) - allowed))
            return ActionResult.failure(
                f"Sirf numbers aur + - * / % ( ) chalega. "
                f"Ye characters allowed nahi: {bad}"
            )

        if "**" in expression:
            try:
                base, _, exponent = expression.partition("**")
                if float(exponent.strip(" ()")) > 100:
                    return ActionResult.failure("Power bahut bada hai, 100 tak hi")
            except ValueError:
                pass

        try:
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
        "better than guessing. Examples: who to message, which option to choose."
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
        ctx.scratch["pending_question"] = question
        return ActionResult.success(
            f"User se poocha: {question}",
            needs_user_input=True,
            question=question,
        )


# ======================================================================
#  JARVIS ADVANCED OS TOOLS
# ======================================================================


class SystemStatusTool(Tool):
    name = "system_status"
    description = (
        "Get live hardware diagnostics: CPU load %, RAM usage, Battery % & charging status, "
        "and primary disk space. Use this when the user asks about laptop/PC health, battery, "
        "memory, or performance."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        lines: list[str] = []
        data: dict[str, Any] = {}

        try:
            import psutil

            # CPU
            cpu_pct = psutil.cpu_percent(interval=0.15)
            cpu_count = psutil.cpu_count(logical=True)
            lines.append(f"CPU Load: {cpu_pct}% ({cpu_count} logical cores)")
            data["cpu_percent"] = cpu_pct

            # RAM
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            lines.append(f"Memory (RAM): {used_gb:.1f} GB / {total_gb:.1f} GB ({mem.percent}% used)")
            data["ram_percent"] = mem.percent

            # Battery
            battery = psutil.sensors_battery()
            if battery:
                plugged_str = "Plugged in (Charging)" if battery.power_plugged else "On Battery (Discharging)"
                lines.append(f"Battery: {battery.percent}% — {plugged_str}")
                data["battery_percent"] = battery.percent
                data["battery_plugged"] = battery.power_plugged
            else:
                lines.append("Battery: Desktop PC / AC Power (No battery detected)")

            # Disk
            root_drive = "C:\\" if sys.platform == "win32" else "/"
            disk = psutil.disk_usage(root_drive)
            free_gb = disk.free / (1024**3)
            total_disk_gb = disk.total / (1024**3)
            lines.append(f"Storage ({root_drive}): {free_gb:.1f} GB free of {total_disk_gb:.1f} GB ({disk.percent}% used)")
            data["disk_free_gb"] = round(free_gb, 1)

            # Top 3 Memory consuming processes
            try:
                procs = []
                for p in psutil.process_iter(["name", "memory_percent"]):
                    try:
                        info = p.info
                        if info["name"] and info["memory_percent"]:
                            procs.append((info["name"], info["memory_percent"]))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                procs.sort(key=lambda x: x[1], reverse=True)
                if procs:
                    top_procs = ", ".join(f"{name} ({pct:.1f}%)" for name, pct in procs[:3])
                    lines.append(f"Top Processes: {top_procs}")
            except Exception:
                pass

        except Exception as exc:  # noqa: BLE001
            lines.append(f"Diagnostics partial fail: {exc}")

        report = "\n".join(lines)
        return ActionResult.success(report, **data)


class VolumeControlTool(Tool):
    name = "volume_control"
    description = (
        "Control system audio volume on laptop/PC. "
        "Action can be: 'set' (level 0-100), 'up' (increase volume), 'down' (decrease volume), "
        "or 'mute' / 'unmute'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["set", "up", "down", "mute", "unmute"],
                "description": "Volume action to perform",
            },
            "level": {
                "type": "integer",
                "description": "Target volume level (0 to 100) when action is 'set'.",
            },
        },
        "required": ["action"],
    }

    async def run(self, ctx: ToolContext, action: str, level: int | None = None) -> ActionResult:
        if sys.platform != "win32":
            return ActionResult.failure("Volume control is currently tuned for Windows.")

        import ctypes

        user32 = ctypes.windll.user32
        VK_VOLUME_MUTE = 0xAD
        VK_VOLUME_DOWN = 0xAE
        VK_VOLUME_UP = 0xAF

        def press(vk: int, times: int = 1):
            for _ in range(times):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, 2, 0)

        action_lower = action.lower().strip()

        if action_lower == "up":
            press(VK_VOLUME_UP, times=5)  # +10%
            return ActionResult.success("Volume badha diya (+10%)")
        elif action_lower == "down":
            press(VK_VOLUME_DOWN, times=5)  # -10%
            return ActionResult.success("Volume kam kar diya (-10%)")
        elif action_lower in ("mute", "unmute"):
            press(VK_VOLUME_MUTE, times=1)
            return ActionResult.success(f"Volume {action_lower} kar diya")
        elif action_lower == "set":
            target = max(0, min(100, int(level if level is not None else 50)))
            # Zero out volume then increase to target
            press(VK_VOLUME_DOWN, times=50)
            press(VK_VOLUME_UP, times=target // 2)
            return ActionResult.success(f"Volume {target}% par set kar diya")

        return ActionResult.failure(f"Unknown volume action: {action}")


class MediaControlTool(Tool):
    name = "media_control"
    description = (
        "Control media playback (Spotify, YouTube, VLC, media player). "
        "Actions: 'play_pause', 'next', 'prev', 'stop'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_pause", "next", "prev", "stop"],
                "description": "Media action to trigger",
            }
        },
        "required": ["action"],
    }

    async def run(self, ctx: ToolContext, action: str) -> ActionResult:
        import ctypes

        user32 = ctypes.windll.user32
        key_map = {
            "play_pause": 0xB3,
            "next": 0xB0,
            "prev": 0xB1,
            "stop": 0xB2,
        }

        vk = key_map.get(action.lower().strip())
        if not vk:
            return ActionResult.failure(f"Unknown media action: {action}")

        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        return ActionResult.success(f"Media command '{action}' triggered successfully.")


class AppControlTool(Tool):
    name = "app_control"
    description = (
        "Manage Windows applications. Actions: 'launch' (open app), 'close' (safely exit app), "
        "or 'list' (list running GUI apps). "
        "Examples: launch 'notepad', launch 'chrome', close 'spotify', close 'calculator'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["launch", "close", "list"],
                "description": "Action to perform",
            },
            "app_name": {
                "type": "string",
                "description": "Name or keyword of the application (e.g. 'notepad', 'chrome', 'spotify')",
            },
        },
        "required": ["action"],
    }

    APP_MAP = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "spotify": "spotify.exe",
        "vscode": "code",
        "code": "code",
        "terminal": "wt.exe",
        "explorer": "explorer.exe",
        "files": "explorer.exe",
        "task manager": "taskmgr.exe",
        "vlc": "vlc.exe",
        "paint": "mspaint.exe",
    }

    async def run(self, ctx: ToolContext, action: str, app_name: str | None = None) -> ActionResult:
        action = action.lower().strip()
        app_name = (app_name or "").lower().strip()

        if action == "launch":
            if not app_name:
                return ActionResult.failure("App ka naam batana zaroori hai.")

            cmd = self.APP_MAP.get(app_name, app_name)
            if sys.platform == "win32":
                subprocess.Popen(f'start "" "{cmd}"', shell=True)
            else:
                subprocess.Popen([cmd])
            return ActionResult.success(f"Application '{app_name}' launch kar diya.")

        elif action == "close":
            if not app_name:
                return ActionResult.failure("Band karne ke liye app ka naam batana zaroori hai.")

            exe_name = self.APP_MAP.get(app_name, app_name)
            if not exe_name.endswith(".exe") and sys.platform == "win32":
                exe_name += ".exe"

            try:
                import psutil

                killed = 0
                for p in psutil.process_iter(["name"]):
                    try:
                        if p.info["name"] and p.info["name"].lower() == exe_name.lower():
                            p.terminate()
                            killed += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if killed > 0:
                    return ActionResult.success(f"'{app_name}' ({killed} process) ko band kar diya.")

                # Fallback to taskkill
                if sys.platform == "win32":
                    res = subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, text=True)
                    if res.returncode == 0:
                        return ActionResult.success(f"'{app_name}' band ho gaya.")

                return ActionResult.failure(f"'{app_name}' running nahi mila.")
            except Exception as exc:  # noqa: BLE001
                return ActionResult.failure(f"App close error: {exc}")

        elif action == "list":
            try:
                import psutil

                gui_apps = set()
                for p in psutil.process_iter(["name"]):
                    try:
                        name = p.info["name"]
                        if name and name.lower() in [
                            "chrome.exe", "firefox.exe", "msedge.exe", "spotify.exe",
                            "code.exe", "notepad.exe", "calc.exe", "explorer.exe",
                            "discord.exe", "telegram.exe", "slack.exe", "vlc.exe",
                        ]:
                            gui_apps.add(name)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if gui_apps:
                    return ActionResult.success("Active apps: " + ", ".join(sorted(gui_apps)))
                return ActionResult.success("Koi common foreground app detected nahi hua.")
            except Exception as exc:  # noqa: BLE001
                return ActionResult.failure(f"List error: {exc}")

        return ActionResult.failure(f"Unknown action: {action}")


class ScreenVisionTool(Tool):
    name = "screen_vision"
    description = (
        "Take an instant screenshot of the computer screen and analyze it with visual intelligence. "
        "Use this when the user asks 'screen dekh ke batao', 'look at my screen', 'read this error', "
        "or questions about what is currently visible on their display."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to analyze or look for on the screen (e.g. 'what error is showing?')",
            }
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str) -> ActionResult:
        # Get desktop device
        desktop = ctx.devices.desktop
        if not desktop:
            return ActionResult.failure("Desktop device available nahi hai.")

        shot_result = await desktop.screenshot()
        if not shot_result.ok or not shot_result.image_b64:
            return ActionResult.failure(f"Screenshot nahi le paya: {shot_result.output}")

        # Send image + query to Vision LLM via Brain
        from ..brain.types import Message

        vision_msg = Message.user(
            f"Screen analysis request: {query}\nAnalyze the attached screenshot accurately.",
            image_b64=shot_result.image_b64,
            image_mime=shot_result.image_mime or "image/png",
        )

        try:
            resp = await ctx.brain.think([vision_msg])
            return ActionResult.success(
                f"Screen Analysis ({resp.provider}):\n{resp.text}",
                analysis=resp.text,
                provider=resp.provider,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Vision model error: {exc}")


class ReminderTool(Tool):
    name = "reminder_set"
    description = (
        "Set a countdown timer or reminder with an alarm. "
        "Example: remind in 10 minutes to 'drink water', or '5 minutes for tea'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "minutes": {
                "type": "number",
                "description": "Duration in minutes (can be float, e.g. 0.5 for 30 seconds)",
            },
            "message": {
                "type": "string",
                "description": "What to remind the user about",
            },
        },
        "required": ["minutes", "message"],
    }

    async def run(self, ctx: ToolContext, minutes: float, message: str) -> ActionResult:
        secs = max(1, int(float(minutes) * 60))

        # Launch async background task for reminder
        async def _reminder_coro(delay: int, text: str):
            await asyncio.sleep(delay)
            # Beep / sound alert
            try:
                if sys.platform == "win32":
                    import winsound
                    for _ in range(3):
                        winsound.Beep(1000, 300)
                        await asyncio.sleep(0.1)
            except Exception:
                pass

        asyncio.create_task(_reminder_coro(secs, message))
        return ActionResult.success(
            f"Reminder set for {minutes} minute(s) ({secs} seconds): '{message}'."
        )


def system_tools() -> list[Tool]:
    """Saare system tools including Jarvis advanced controls."""
    return [
        TimeTool(),
        CalculateTool(),
        AskUserTool(),
        SystemStatusTool(),
        VolumeControlTool(),
        MediaControlTool(),
        AppControlTool(),
        ScreenVisionTool(),
        ReminderTool(),
    ]
