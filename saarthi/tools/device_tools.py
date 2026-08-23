"""
Device Tools — agent ke haath.

Ye tools kisi bhi device pe kaam karte hain (Android, laptop, jo bhi).
Device manager decide karta hai kaunsa device use hoga.

IMPORTANT design decision:
    Agent ko blind coordinates pe tap karne se rokna hai.
    Isliye order ye hai:
      1. Pehle screen_padho (ui_tree) — sasta, fast, exact
      2. Phir tap_text (text se element dhoondh ke tap)
      3. Screenshot sirf tab jab structure se kaam na bane
      4. Raw coordinates sabse last option

Isse reliability badhti hai aur free-tier tokens bachte hain.
"""

from __future__ import annotations

from ..devices.base import ActionResult, Capability
from .base import Tool, ToolContext
from .safety import check_shell_safety, check_text_safety


def _resolve_device(ctx: ToolContext, device: str | None):
    """Device dhoondo, warna clear error do."""
    dev = ctx.devices.get(device)
    if dev is None:
        available = ", ".join(ctx.devices.devices) or "koi nahi"
        return None, ActionResult.failure(
            f"'{device}' naam ka device nahi mila. Available: {available}"
        )
    return dev, None


# Common parameter — har device tool mein hai
DEVICE_PARAM = {
    "device": {
        "type": "string",
        "description": (
            "Kis device pe kaam karna hai: 'android' (phone) ya 'desktop' "
            "(laptop). Na do to default use hoga."
        ),
    }
}


# ======================================================================
#  Screen reading — ye pehle use karna chahiye
# ======================================================================


class ReadScreenTool(Tool):
    name = "screen_padho"
    description = (
        "Screen pe kya hai wo padho — saara text, buttons, input fields "
        "aur unke coordinates. SCREENSHOT SE PEHLE YE USE KAR: ye fast hai, "
        "sasta hai, aur exact text deta hai. Kisi bhi UI pe kaam karne se "
        "pehle pehla step yahi hona chahiye."
    )
    parameters = {"type": "object", "properties": dict(DEVICE_PARAM)}
    requires_capability = Capability.UI_TREE

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error

        if not dev.can(Capability.UI_TREE):
            return ActionResult.failure(
                f"'{dev.name}' ka screen structure padh nahi sakta. "
                f"screenshot_lo try kar."
            )

        return await dev.ui_tree()


class ScreenshotTool(Tool):
    name = "screenshot_lo"
    description = (
        "Screen ki photo lo taaki tu dekh sake. Tab use kar jab "
        "screen_padho se kaam na bane — jaise image dekhni ho, ya layout "
        "samajhna ho. Dhyan: ye zyada tokens kha jaata hai, isliye "
        "pehle screen_padho try kar."
    )
    parameters = {"type": "object", "properties": dict(DEVICE_PARAM)}
    requires_capability = Capability.SCREENSHOT

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.screenshot()


# ======================================================================
#  Interaction
# ======================================================================


class TapTextTool(Tool):
    name = "text_pe_tap"
    description = (
        "Screen pe likhe text/button pe tap karo. YE PREFERRED TAREEKA HAI "
        "— coordinates se behtar hai, kyunki UI badal jaaye ya screen size "
        "alag ho to bhi kaam karta hai. Example: text='Recharge'"
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Button ya element ka text jispe tap karna hai",
            },
            **DEVICE_PARAM,
        },
        "required": ["text"],
    }
    requires_capability = Capability.TAP

    async def run(
        self, ctx: ToolContext, text: str, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.tap_text(text)


class TapTool(Tool):
    name = "coordinate_pe_tap"
    description = (
        "Exact x,y coordinate pe tap karo. YE LAST OPTION HAI — pehle "
        "text_pe_tap try kar. Coordinates sirf tab use kar jab screen_padho "
        "se element mila ho aur uske coordinates pata hon."
    )
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate"},
            "y": {"type": "integer", "description": "Y coordinate"},
            **DEVICE_PARAM,
        },
        "required": ["x", "y"],
    }
    requires_capability = Capability.TAP

    async def run(
        self, ctx: ToolContext, x: int, y: int, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.tap(int(x), int(y))


class TypeTextTool(Tool):
    name = "text_likho"
    description = (
        "Jo field select hai usme text type karo. Pehle us field pe tap "
        "karna zaroori hai. Password/OTP/PIN type karne se main mana kar "
        "dunga — wo user khud daalega."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Jo likhna hai"},
            **DEVICE_PARAM,
        },
        "required": ["text"],
    }
    requires_capability = Capability.TYPE

    async def run(
        self, ctx: ToolContext, text: str, device: str | None = None
    ) -> ActionResult:
        # SAFETY: password/OTP block karo
        verdict = check_text_safety(text)
        if verdict.is_blocked:
            return ActionResult.failure(verdict.reason)

        if verdict.needs_confirmation:
            approved = await ctx.ask_confirmation(
                "Ye text type karna hai", {"text": text, "wajah": verdict.reason}
            )
            if not approved:
                return ActionResult.failure("User ne mana kar diya")

        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.type_text(text)


class PressKeyTool(Tool):
    name = "key_dabao"
    description = (
        "Hardware ya special key dabao. Android: back/home/enter/recent/"
        "volume_up/volume_down/power. Desktop: enter/tab/esc ya combo "
        "jaise 'ctrl+c'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key ka naam, jaise 'back', 'home', 'enter'",
            },
            **DEVICE_PARAM,
        },
        "required": ["key"],
    }
    requires_capability = Capability.KEY

    async def run(
        self, ctx: ToolContext, key: str, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.press_key(key)


class ScrollTool(Tool):
    name = "scroll_karo"
    description = (
        "Screen scroll karo. Direction: down/up/left/right (ya neeche/upar/"
        "baayen/daayen). Screen size ke hisaab se automatically calculate "
        "hota hai, isliye har phone pe kaam karta hai."
    )
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "description": "down, up, left, ya right",
            },
            "amount": {
                "type": "number",
                "description": "Kitna scroll (0.1 se 0.8, default 0.5)",
            },
            **DEVICE_PARAM,
        },
        "required": ["direction"],
    }
    requires_capability = Capability.SWIPE

    async def run(
        self,
        ctx: ToolContext,
        direction: str,
        amount: float = 0.5,
        device: str | None = None,
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error

        # Android ke paas smart scroll hai
        scroll = getattr(dev, "scroll", None)
        if scroll is not None:
            return await scroll(direction=direction, amount=amount)

        return ActionResult.failure(f"'{dev.name}' pe scroll support nahi hai")


# ======================================================================
#  App management
# ======================================================================


class LaunchAppTool(Tool):
    name = "app_kholo"
    description = (
        "App kholo. Aam naam chalega — 'paytm', 'whatsapp', 'irctc', "
        "'swiggy' — package name khud resolve ho jaayega. Indian apps ka "
        "pura database built-in hai."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "App ka naam, jaise 'paytm' ya 'whatsapp'",
            },
            **DEVICE_PARAM,
        },
        "required": ["app"],
    }
    requires_capability = Capability.LAUNCH_APP

    async def run(
        self, ctx: ToolContext, app: str, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.launch_app(app)


class CloseAppTool(Tool):
    name = "app_band_karo"
    description = "Chalta hua app band karo (force stop)."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "App ka naam"},
            **DEVICE_PARAM,
        },
        "required": ["app"],
    }
    requires_capability = Capability.CLOSE_APP

    async def run(
        self, ctx: ToolContext, app: str, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.close_app(app)


class ListAppsTool(Tool):
    name = "apps_ki_list"
    description = (
        "Device pe kaunse apps installed hain wo batao. Tab use kar jab "
        "app khulne mein problem aaye — check kar sakte hain ki app hai ya nahi."
    )
    parameters = {"type": "object", "properties": dict(DEVICE_PARAM)}
    requires_capability = Capability.LIST_APPS

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.list_apps()


# ======================================================================
#  Device info & shell
# ======================================================================


class DeviceInfoTool(Tool):
    name = "device_ki_jaankari"
    description = (
        "Device ki info batao — model, Android version, battery, screen "
        "size. Ya sab devices ki status dekho."
    )
    parameters = {
        "type": "object",
        "properties": {
            "device": {
                "type": "string",
                "description": (
                    "Kis device ki info. 'all' do to sab devices ki status."
                ),
            }
        },
    }

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        if device == "all" or device is None:
            summary = await ctx.devices.describe()
            return ActionResult.success(summary)

        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.info()


class ShellTool(Tool):
    name = "command_chalao"
    description = (
        "Shell/terminal command chalao. Desktop pe files dhoondhne, "
        "system info, ya programs chalane ke liye. Khatarnak commands "
        "automatically block ho jaate hain."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command"},
            **DEVICE_PARAM,
        },
        "required": ["command"],
    }
    risky = True  # Har shell command pe confirmation
    requires_capability = Capability.SHELL

    async def run(
        self, ctx: ToolContext, command: str, device: str | None = None
    ) -> ActionResult:
        # SAFETY: hard blocks pehle
        verdict = check_shell_safety(command)
        if verdict.is_blocked:
            return ActionResult.failure(
                f"Ye command block hai: {verdict.reason}. Main ye nahi chalaunga."
            )

        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.run_shell(command)


class NotificationsTool(Tool):
    name = "notifications_padho"
    description = "Phone ke notifications padho — kya aaya hai wo batao."
    parameters = {"type": "object", "properties": dict(DEVICE_PARAM)}
    requires_capability = Capability.NOTIFICATIONS

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error
        return await dev.read_notifications()


# ======================================================================
#  Registration helper
# ======================================================================


def device_tools() -> list[Tool]:
    """Saare device tools ki list."""
    return [
        # Reading — pehle ye
        ReadScreenTool(),
        ScreenshotTool(),
        DeviceInfoTool(),
        NotificationsTool(),
        # Interaction
        TapTextTool(),
        TapTool(),
        TypeTextTool(),
        PressKeyTool(),
        ScrollTool(),
        # Apps
        LaunchAppTool(),
        CloseAppTool(),
        ListAppsTool(),
        # Power tools
        ShellTool(),
    ]
