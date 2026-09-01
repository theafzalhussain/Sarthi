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

import logging

from ..devices.base import ActionResult, Capability
from .banking import check_app_allowed, screenshot_allowed
from .base import Tool, ToolContext
from .redact import redact_sensitive, redaction_note
from .safety import check_shell_safety, check_text_safety

log = logging.getLogger("saarthi.tools.device")


def _resolve_device(ctx: ToolContext, device: str | None):
    """Device dhoondo, warna clear error do.
    
    SMART ROUTING: Agar device specify nahi kiya aur default device
    pe capability nahi hai (jaise desktop pe screenshot/key_dabao), par
    browser active hai — to browser pe route kar do automatically.
    """
    dev = ctx.devices.get(device)
    if dev is None:
        available = ", ".join(ctx.devices.devices) or "koi nahi"
        return None, ActionResult.failure(
            f"'{device}' naam ka device nahi mila. Available: {available}"
        )
    return dev, None


def _resolve_device_smart(ctx: ToolContext, device: str | None, capability: Capability | None = None):
    """
    Smart device resolution — browser pe auto-route jab desktop fail hoga.
    
    Ye fix karta hai wo problem jab agent browser mein kaam kar raha hai
    (YouTube khola, page padha) par key_dabao/screenshot_lo default device
    (desktop) pe jaata hai aur fail hota hai.
    """
    dev = ctx.devices.get(device)
    if dev is None:
        available = ", ".join(ctx.devices.devices) or "koi nahi"
        return None, ActionResult.failure(
            f"'{device}' naam ka device nahi mila. Available: {available}"
        )
    
    # Smart routing: device explicitly diya hai to wahi use karo
    if device is not None:
        return dev, None
    
    # Default device pe capability nahi hai? Browser try karo.
    if capability and not dev.can(capability):
        browser = ctx.devices.get("browser")
        if browser is not None and browser.can(capability):
            return browser, None
    
    return dev, None


# Ye apps browser mein bhi khul jaate hain — phone na ho to laptop pe
# website khol ke kaam ho jaata hai.
WEB_FALLBACK_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "whatsapp": "https://web.whatsapp.com",
    "wa": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "insta": "https://www.instagram.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "map": "https://maps.google.com",
    "irctc": "https://www.irctc.co.in",
    "flipkart": "https://www.flipkart.com",
    "amazon": "https://www.amazon.in",
    "zomato": "https://www.zomato.com",
    "swiggy": "https://www.swiggy.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "linkedin": "https://www.linkedin.com",
    "facebook": "https://www.facebook.com",
    "fb": "https://www.facebook.com",
    "netflix": "https://www.netflix.com",
    "hotstar": "https://www.hotstar.com",
    "spotify": "https://open.spotify.com",
    "paytm": "https://paytm.com",
    "digilocker": "https://www.digilocker.gov.in",
    "chrome": "https://www.google.com",
    "browser": "https://www.google.com",
    "youtube music": "https://music.youtube.com",
}


def _web_fallback_hint(app: str) -> str:
    """
    Phone na ho to LLM ko batao ki laptop pe website se kaam ho sakta hai.

    Ye ek asli problem thi: user ne "youtube pe song play kar do" bola,
    phone connected nahi tha, aur agent ne haar maan li — jabki laptop
    pe browser se aaram se ho jaata.
    """
    url = WEB_FALLBACK_URLS.get(app.strip().lower())
    if not url:
        return ""
    return (
        f"\n  ALTERNATIVE: '{app}' website se bhi khul jaata hai. "
        f"Phone connected nahi hai to laptop pe kholo — "
        f"command_chalao se: start {url}  (device='desktop')"
    )


# Common parameter — har device tool mein hai
DEVICE_PARAM = {
    "device": {
        "type": "string",
        "enum": ["browser", "android", "phone", "desktop"],
        "description": (
            "Kis device pe kaam karna hai:\n"
            "- 'browser' -> jo website tune website_kholo se kholi (YouTube, "
            "Gmail, WhatsApp Web, koi bhi site). WEBSITE KHOLNE KE BAAD PADHNE/"
            "TAP KARNE KE LIYE HAMESHA 'browser' USE KAR — 'desktop' NAHI.\n"
            "- 'android' / 'phone' -> connected phone.\n"
            "- 'desktop' -> laptop ki poori screen (desktop apps ke liye, "
            "browser page ke liye NAHI).\n"
            "Na do to default use hoga."
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

        result = await dev.ui_tree()

        # --- SENSITIVE DATA HATAO (LLM ko bhejne se PEHLE) ---
        #
        # Ye YAHIN hona chahiye, device layer mein NAHI.
        #
        # Wajah: `tap_text("Send Money")` ko ASLI text chahiye element
        # dhoondhne ke liye. Device layer pe redact kar dete to tapping
        # hi tut jaati. Leak ka raasta LLM tha (ye `output` string), aur
        # device ka raw data nahi.
        if result.ok and result.output:
            clean, found = redact_sensitive(result.output)
            if found:
                log.info("screen_padho: %s redact kiya", ", ".join(found))
                result.output = clean + redaction_note(found)

        return result


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
        dev, error = _resolve_device_smart(ctx, device, Capability.SCREENSHOT)
        if error:
            return error

        # --- BANKING LOCK: banking app saamne ho to screenshot nahi ---
        #
        # Screenshot pe khaas rok kyun: redaction TEXT pe lagti hai,
        # IMAGE pe nahi lag sakti. Screenshot mein card number aur
        # balance saaf dikhta hai aur wo seedha vision model ko chala
        # jaata hai. Text redact karke image bhej dena bekaar hai.
        current = ""
        get_current = getattr(dev, "current_app", None)
        if get_current is not None:
            try:
                app_result = await get_current()
                current = (app_result.output or "") if app_result.ok else ""
            except Exception:  # noqa: BLE001 — pata na chale to allow (documented)
                current = ""

        allowed, reason = screenshot_allowed(current)
        if not allowed:
            log.warning("screenshot_lo blocked (banking app: %s)", current)
            return ActionResult.failure(reason)

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
        dev, error = _resolve_device_smart(ctx, device, Capability.TAP)
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
        "jaise 'ctrl+c'. Browser mein bhi kaam karta hai (space=play/pause)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key ka naam, jaise 'back', 'home', 'enter', 'space'",
            },
            **DEVICE_PARAM,
        },
        "required": ["key"],
    }
    requires_capability = Capability.KEY

    async def run(
        self, ctx: ToolContext, key: str, device: str | None = None
    ) -> ActionResult:
        dev, error = _resolve_device_smart(ctx, device, Capability.KEY)
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
        # --- BANKING LOCK / BLOCKED APPS ---
        #
        # Ye check SABSE PEHLE hai — device resolve karne se bhi pehle.
        # Wajah: blocked app ke liye device dhoondhna, availability check
        # karna, package resolve karna — sab bekaar kaam hai. Aur agar
        # baad mein check hota to koi naya code path usse bypass kar
        # sakta tha. Security check pehla hona chahiye.
        allowed, reason = check_app_allowed(app)
        if not allowed:
            log.warning("app_kholo blocked: %s", app)
            return ActionResult.failure(reason)

        dev, error = _resolve_device(ctx, device)
        if error:
            return error

        # Android maanga par connected nahi hai? Pehle hi bata do +
        # web alternative suggest karo. Warna agent 3 tools try karke
        # haar maan leta hai (asli bug tha).
        if dev.kind == "android" and not await dev.is_available():
            hint = _web_fallback_hint(app)
            return ActionResult.failure(
                f"Phone connected nahi hai, isliye '{app}' phone pe nahi "
                f"khul sakta.\n"
                f"  Phone use karna hai to: USB laga + USB Debugging ON + "
                f"'adb devices' check kar." + hint
            )

        result = await dev.launch_app(app)

        # App khulne mein fail hua aur website available hai to bata do
        if not result.ok:
            hint = _web_fallback_hint(app)
            if hint:
                return ActionResult.failure(result.error + hint)

        return result


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


class ConnectPhoneWifiTool(Tool):
    name = "phone_wifi_se_jodo"
    description = (
        "Phone ko WiFi se connect karo (USB cable ke bina). "
        "PEHLE EK BAAR USB cable lagana zaroori hai — uske baad cable "
        "nikaal sakte hain. Phone aur laptop same WiFi pe hone chahiye. "
        "Phone ka IP chahiye (phone ke Settings > About > Status mein milta hai), "
        "ya khali chhod de to khud dhoondhne ki koshish karunga."
    )
    parameters = {
        "type": "object",
        "properties": {
            "ip": {
                "type": "string",
                "description": "Phone ka IP, jaise '192.168.1.5'. Na pata ho to khali chhod",
            },
            "port": {
                "type": "integer",
                "description": "Port (default 5555)",
            },
        },
    }
    risky = True  # Network connection bana raha hai

    async def run(
        self,
        ctx: ToolContext,
        ip: str | None = None,
        port: int = 5555,
    ) -> ActionResult:
        android = ctx.devices.get("android")
        if android is None:
            return ActionResult.failure("Android device register nahi hai")

        adb = getattr(android, "_adb", None)
        if adb is None:
            return ActionResult.failure("Ye tool sirf ADB wale device pe chalta hai")

        steps: list[str] = []

        # IP na diya ho to phone se hi pucho (USB connected hona chahiye)
        if not ip:
            probe = await adb(
                ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"], timeout=15.0
            )
            if probe.ok and probe.output:
                import re

                match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", probe.output)
                if match:
                    ip = match.group(1)
                    steps.append(f"Phone ka IP mila: {ip}")

        if not ip:
            return ActionResult.failure(
                "Phone ka IP nahi mila.\n"
                "  1. Pehle USB cable laga (ek baar zaroori hai)\n"
                "  2. Ya phone mein dekh: Settings > About phone > Status > IP address\n"
                "  3. Phir dobara bol: 'phone ko wifi se jodo, IP 192.168.1.5'"
            )

        # TCP mode ON karo (iske liye USB connection chahiye)
        tcp = await adb(["tcpip", str(port)], timeout=20.0)
        if not tcp.ok:
            return ActionResult.failure(
                f"TCP mode ON nahi hua: {tcp.error}\n"
                f"  USB cable laga hua hai? 'adb devices' se check kar."
            )
        steps.append(f"TCP mode ON (port {port})")

        # Connect karo
        import asyncio as _asyncio

        await _asyncio.sleep(1.5)
        connect = await adb(["connect", f"{ip}:{port}"], timeout=25.0)

        if not connect.ok or "unable" in (connect.output or "").lower():
            return ActionResult.failure(
                f"Connect nahi hua: {connect.output or connect.error}\n"
                f"  Phone aur laptop SAME WiFi pe hain? Check kar."
            )

        steps.append(f"Connected: {ip}:{port}")
        ctx.devices.invalidate_cache()

        return ActionResult.success(
            "Phone WiFi se jud gaya!\n  "
            + "\n  ".join(steps)
            + "\n\n  Ab USB cable nikaal sakta hai. "
            "Phone restart hone pe dobara jodna padega."
        )


class NotificationsTool(Tool):
    name = "notifications_padho"
    description = "Phone ke notifications padho — kya aaya hai wo batao."
    parameters = {"type": "object", "properties": dict(DEVICE_PARAM)}
    requires_capability = Capability.NOTIFICATIONS

    async def run(self, ctx: ToolContext, device: str | None = None) -> ActionResult:
        dev, error = _resolve_device(ctx, device)
        if error:
            return error

        result = await dev.read_notifications()

        # Notifications mein OTP aata hai — ye sabse zaroori redaction
        # point hai. Android ki apni redaction pehla layer hai
        # (`--noredact` hataya gaya), ye doosra.
        if result.ok and result.output:
            clean, found = redact_sensitive(result.output)
            if found:
                log.info("notifications_padho: %s redact kiya", ", ".join(found))
                result.output = clean + redaction_note(found)

        return result


# ======================================================================
#  Registration helper
# ======================================================================


class FillFieldTool(Tool):
    name = "field_bharo"
    description = (
        "Browser mein koi input field bharo — label, placeholder ya naam se "
        "dhoondh ke. Form bharne ke liye ye BEST hai (tap + type se behtar). "
        "Example: field='email', value='abc@gmail.com'"
    )
    parameters = {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "description": "Field ka label/placeholder, jaise 'Search' ya 'email'",
            },
            "value": {"type": "string", "description": "Kya bharna hai"},
            **DEVICE_PARAM,
        },
        "required": ["field", "value"],
    }

    async def run(
        self,
        ctx: ToolContext,
        field: str,
        value: str,
        device: str | None = None,
    ) -> ActionResult:
        # SAFETY: password/OTP yahan bhi block
        verdict = check_text_safety(value)
        if verdict.is_blocked:
            return ActionResult.failure(verdict.reason)

        dev, error = _resolve_device(ctx, device or "browser")
        if error:
            return error

        filler = getattr(dev, "fill_field", None)
        if filler is None:
            return ActionResult.failure(
                f"'{dev.name}' pe field_bharo support nahi hai. "
                f"text_pe_tap phir text_likho use kar."
            )
        return await filler(field, value)


class ReadPageTool(Tool):
    name = "page_padho"
    description = (
        "Browser mein khule page ka pura text padho. Website ka content "
        "samajhne ke liye — news, article, search results, prices. "
        "screen_padho buttons dikhata hai, ye pura CONTENT deta hai."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_chars": {
                "type": "integer",
                "description": "Max kitna text (default 6000)",
            },
            **DEVICE_PARAM,
        },
    }

    async def run(
        self,
        ctx: ToolContext,
        max_chars: int = 6000,
        device: str | None = None,
    ) -> ActionResult:
        dev, error = _resolve_device(ctx, device or "browser")
        if error:
            return error

        reader = getattr(dev, "read_page", None)
        if reader is None:
            return ActionResult.failure(
                f"'{dev.name}' pe page_padho support nahi hai (ye browser "
                f"ke liye hai)"
            )

        result = await reader(max_chars=max_chars)

        # Banking WEBSITE bhi utni hi khatarnak hai jitni app.
        # netbanking.hdfcbank.com ka page text bhi LLM ko jaata hai —
        # usme account number aur balance hota hai. Isliye yahan bhi
        # redaction, sirf phone screen pe nahi.
        if result.ok and result.output:
            clean, found = redact_sensitive(result.output)
            if found:
                log.info("page_padho: %s redact kiya", ", ".join(found))
                result.output = clean + redaction_note(found)

        return result


def device_tools() -> list[Tool]:
    """Saare device tools ki list."""
    return [
        # Reading — pehle ye
        ReadScreenTool(),
        ScreenshotTool(),
        ReadPageTool(),
        DeviceInfoTool(),
        NotificationsTool(),
        ConnectPhoneWifiTool(),
        # Interaction
        TapTextTool(),
        TapTool(),
        TypeTextTool(),
        FillFieldTool(),
        PressKeyTool(),
        ScrollTool(),
        # Apps
        LaunchAppTool(),
        CloseAppTool(),
        ListAppsTool(),
        # Power tools
        ShellTool(),
    ]
