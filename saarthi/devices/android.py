"""
Android Device Adapter — ADB ke through.

Ye SAARTHI ka pehla asli "haath" hai. Isse laptop se phone control hota hai.

SETUP (ek baar karna hai):
    1. Phone: Settings -> About phone -> Build number pe 7 baar tap
       (Developer Options unlock ho jaayega)
    2. Settings -> Developer options -> USB Debugging ON
    3. Laptop se USB cable se jodo
    4. Terminal: adb devices
       -> phone pe popup aayega "Allow USB debugging?" -> Allow
    5. Ho gaya! Test kar: adb shell input tap 500 500

WIFI PE (cable ke bina):
    adb tcpip 5555
    adb connect <phone-ka-ip>:5555

NOTE: Ye Phase 3 ka tareeka hai (laptop se phone). Phase 4 mein
hum Android app banayenge jo Accessibility Service use karega —
tab laptop ki zarurat nahi padegi.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import shutil
import xml.etree.ElementTree as ET

from ..config import settings as default_settings
from .base import ActionResult, Capability, Device, UIElement

log = logging.getLogger("saarthi.devices.android")

# Hinglish/simple key naam -> Android keycode
KEY_MAP: dict[str, str] = {
    "home": "KEYCODE_HOME",
    "back": "KEYCODE_BACK",
    "peeche": "KEYCODE_BACK",
    "wapas": "KEYCODE_BACK",
    "recent": "KEYCODE_APP_SWITCH",
    "enter": "KEYCODE_ENTER",
    "search": "KEYCODE_SEARCH",
    "delete": "KEYCODE_DEL",
    "backspace": "KEYCODE_DEL",
    "tab": "KEYCODE_TAB",
    "space": "KEYCODE_SPACE",
    "power": "KEYCODE_POWER",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "mute": "KEYCODE_VOLUME_MUTE",
    "camera": "KEYCODE_CAMERA",
    "call": "KEYCODE_CALL",
    "endcall": "KEYCODE_ENDCALL",
    "menu": "KEYCODE_MENU",
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "wake": "KEYCODE_WAKEUP",
    "sleep": "KEYCODE_SLEEP",
}


def _escape_adb_text(text: str) -> str:
    """
    `adb shell input text` ke liye text safe banao.

    ADB space ko handle nahi karta — %s use karna padta hai.
    Aur shell special characters escape karne padte hain.
    """
    # Pehle backslash (warna baaki escapes double ho jaayenge)
    escaped = text.replace("\\", "\\\\")

    for char in ['"', "'", "(", ")", "&", "<", ">", "|", ";", "*", "~", "`", "$"]:
        escaped = escaped.replace(char, f"\\{char}")

    # Space -> %s (ADB ka apna convention)
    return escaped.replace(" ", "%s")


def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
    """
    ADB ka bounds format parse karo: "[0,100][500,200]"

    Returns: (left, top, right, bottom)
    """
    numbers = re.findall(r"-?\d+", bounds_str or "")
    if len(numbers) >= 4:
        return (
            int(numbers[0]),
            int(numbers[1]),
            int(numbers[2]),
            int(numbers[3]),
        )
    return (0, 0, 0, 0)


class AndroidDevice(Device):
    """Android phone, ADB ke through control."""

    kind = "android"
    capabilities = {
        Capability.TAP,
        Capability.SWIPE,
        Capability.TYPE,
        Capability.KEY,
        Capability.SCREENSHOT,
        Capability.UI_TREE,
        Capability.LAUNCH_APP,
        Capability.CLOSE_APP,
        Capability.LIST_APPS,
        Capability.SHELL,
        Capability.NOTIFICATIONS,
        Capability.DEVICE_INFO,
    }

    def __init__(
        self,
        name: str = "android",
        adb_path: str | None = None,
        serial: str | None = None,
    ):
        super().__init__(name)
        self.adb_path = adb_path or default_settings.adb_path
        self.serial = serial  # Multiple phones ho to konsa

    # ------------------------------------------------------------------
    #  ADB plumbing
    # ------------------------------------------------------------------

    def _build_args(self, args: list[str]) -> list[str]:
        """ADB command banao, serial ke saath agar diya hai."""
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd + args

    async def _adb_raw(
        self, args: list[str], timeout: float = 30.0
    ) -> tuple[int, bytes, bytes]:
        """
        ADB chalao, raw bytes return karo.

        Binary output (screenshot) ke liye bytes zaroori hai.
        """
        cmd = self._build_args(args)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"ADB nahi mila ('{self.adb_path}').\n"
                "Install kar: https://developer.android.com/tools/releases/platform-tools\n"
                "Ya .env mein ADB_PATH set kar."
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError(f"ADB command timeout ({timeout}s): {' '.join(args)}")

        return process.returncode or 0, stdout, stderr

    async def _adb(self, args: list[str], timeout: float = 30.0) -> ActionResult:
        """ADB chalao, text result return karo."""
        try:
            code, stdout, stderr = await self._adb_raw(args, timeout)
        except (FileNotFoundError, TimeoutError) as exc:
            return ActionResult.failure(str(exc))
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"ADB error: {exc}")

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if code != 0:
            return ActionResult.failure(err or out or f"ADB exit code {code}")

        # ADB kabhi kabhi error stderr pe deta hai par exit 0 return karta hai
        if err and "error" in err.lower():
            return ActionResult.failure(err)

        return ActionResult.success(out)

    async def _shell(self, command: str, timeout: float = 30.0) -> ActionResult:
        """Phone pe shell command chalao."""
        return await self._adb(["shell", command], timeout)

    # ------------------------------------------------------------------
    #  Connection
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Phone connected hai?"""
        if not shutil.which(self.adb_path) and "/" not in self.adb_path:
            return False

        result = await self._adb(["devices"], timeout=10.0)
        if not result.ok:
            return False

        # Output: "List of devices attached\nABC123\tdevice"
        for line in result.output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                if self.serial is None or parts[0] == self.serial:
                    return True
        return False

    async def info(self) -> ActionResult:
        """Phone ki jaankari — model, Android version, battery, screen size."""
        if not await self.is_available():
            return ActionResult.failure(
                "Phone connected nahi hai.\n"
                "  1. USB cable laga\n"
                "  2. Developer Options -> USB Debugging ON kar\n"
                "  3. Phone pe 'Allow USB debugging' Allow kar\n"
                "  4. Check kar: adb devices"
            )

        details: dict[str, str] = {}

        probes = {
            "model": "getprop ro.product.model",
            "brand": "getprop ro.product.brand",
            "android_version": "getprop ro.build.version.release",
            "screen": "wm size",
        }

        for key, command in probes.items():
            result = await self._shell(command, timeout=10.0)
            if result.ok and result.output:
                details[key] = result.output.strip()

        # Battery percentage
        battery = await self._shell("dumpsys battery | grep level", timeout=10.0)
        if battery.ok:
            match = re.search(r"level:\s*(\d+)", battery.output)
            if match:
                details["battery"] = f"{match.group(1)}%"

        # Screen size clean karo: "Physical size: 1080x2400" -> "1080x2400"
        if "screen" in details:
            match = re.search(r"(\d+x\d+)", details["screen"])
            if match:
                details["screen"] = match.group(1)

        summary = ", ".join(f"{k}={v}" for k, v in details.items())
        return ActionResult.success(summary or "connected", **details)

    async def screen_size(self) -> tuple[int, int] | None:
        """Screen ka resolution — swipe calculations ke liye kaam aata hai."""
        result = await self._shell("wm size", timeout=10.0)
        if not result.ok:
            return None
        match = re.search(r"(\d+)x(\d+)", result.output)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return None

    # ------------------------------------------------------------------
    #  Input actions
    # ------------------------------------------------------------------

    async def tap(self, x: int, y: int) -> ActionResult:
        result = await self._shell(f"input tap {int(x)} {int(y)}")
        if result.ok:
            return ActionResult.success(f"tap kiya ({x},{y})")
        return result

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> ActionResult:
        result = await self._shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}"
        )
        if result.ok:
            return ActionResult.success(f"swipe kiya ({x1},{y1}) -> ({x2},{y2})")
        return result

    async def scroll(self, direction: str = "down", amount: float = 0.5) -> ActionResult:
        """
        Screen scroll karo — screen size ke hisaab se, hardcoded nahi.

        Ye budget phones pe bhi sahi chalega (PILLAR #3), kyunki
        coordinates screen size se calculate hote hain.
        """
        size = await self.screen_size()
        if size is None:
            return ActionResult.failure("Screen size nahi mila")

        width, height = size
        cx = width // 2
        span = int(height * max(0.1, min(amount, 0.8)))

        mid = height // 2
        if direction in ("down", "neeche"):
            # Neeche dekhne ke liye upar swipe karna padta hai
            return await self.swipe(cx, mid + span // 2, cx, mid - span // 2)
        if direction in ("up", "upar"):
            return await self.swipe(cx, mid - span // 2, cx, mid + span // 2)
        if direction in ("left", "baayen"):
            return await self.swipe(cx + span // 2, mid, cx - span // 2, mid)
        if direction in ("right", "daayen"):
            return await self.swipe(cx - span // 2, mid, cx + span // 2, mid)

        return ActionResult.failure(
            f"Direction samajh nahi aaya: {direction} "
            "(down/up/left/right ya neeche/upar/baayen/daayen)"
        )

    async def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult.failure("Khali text type nahi kar sakte")

        result = await self._shell(f"input text {_escape_adb_text(text)}")
        if result.ok:
            return ActionResult.success(f"type kiya: {text[:60]}")
        return result

    async def press_key(self, key: str) -> ActionResult:
        keycode = KEY_MAP.get(key.lower().strip(), key.upper().strip())

        # User ne "back" diya to "KEYCODE_BACK" banao
        if not keycode.startswith("KEYCODE_") and not keycode.isdigit():
            keycode = f"KEYCODE_{keycode}"

        result = await self._shell(f"input keyevent {keycode}")
        if result.ok:
            return ActionResult.success(f"{key} press kiya")
        return result

    # ------------------------------------------------------------------
    #  Screen reading
    # ------------------------------------------------------------------

    async def screenshot(self) -> ActionResult:
        """
        Screenshot lo, base64 PNG return karo.

        Ye Gemini ko bheja jaata hai — wahi "aankh" hai jo screen samajhta hai.
        """
        try:
            code, stdout, stderr = await self._adb_raw(
                ["exec-out", "screencap", "-p"], timeout=45.0
            )
        except (FileNotFoundError, TimeoutError) as exc:
            return ActionResult.failure(str(exc))

        if code != 0 or not stdout:
            err = stderr.decode("utf-8", errors="replace").strip()
            return ActionResult.failure(err or "Screenshot nahi mila")

        # PNG magic bytes check
        if not stdout.startswith(b"\x89PNG"):
            return ActionResult.failure("Screenshot corrupt hai (PNG nahi hai)")

        return ActionResult.success(
            f"Screenshot liya ({len(stdout) // 1024} KB)",
            image_b64=base64.b64encode(stdout).decode("ascii"),
            image_mime="image/png",
        )

    async def ui_tree(self) -> ActionResult:
        """
        Screen ka structure padho — text, buttons, inputs sab.

        Ye screenshot se BEHTAR hai kai baar:
          - Text exactly milta hai (OCR ki galti nahi)
          - Coordinates exact milte hain
          - Bahut kam data (free tier tokens bachte hain!)
          - Budget phones pe fast (PILLAR #3)

        Isliye SAARTHI pehle ui_tree try karta hai, screenshot baad mein.
        """
        # uiautomator XML dump karta hai
        dump = await self._shell(
            "uiautomator dump /sdcard/saarthi_ui.xml", timeout=45.0
        )
        if not dump.ok:
            return ActionResult.failure(f"UI dump fail: {dump.error}")

        read = await self._shell("cat /sdcard/saarthi_ui.xml", timeout=30.0)
        if not read.ok or not read.output:
            return ActionResult.failure("UI XML padh nahi paye")

        # Cleanup — phone pe kachra nahi chhodna
        await self._shell("rm -f /sdcard/saarthi_ui.xml", timeout=10.0)

        try:
            elements = self._parse_ui_xml(read.output)
        except ET.ParseError as exc:
            return ActionResult.failure(f"UI XML kharab hai: {exc}")

        interactive = [el for el in elements if el.clickable or el.editable]

        summary_lines = [f"Screen pe {len(elements)} elements mile"]
        if interactive:
            summary_lines.append("Interactive elements:")
            for el in interactive[:25]:
                summary_lines.append(f"  - {el}")

        return ActionResult.success(
            "\n".join(summary_lines),
            elements=elements,
            interactive=interactive,
        )

    def _parse_ui_xml(self, xml_text: str) -> list[UIElement]:
        """uiautomator ka XML -> UIElement list."""
        root = ET.fromstring(xml_text)
        elements: list[UIElement] = []

        for node in root.iter("node"):
            attrib = node.attrib

            text = (attrib.get("text") or "").strip()
            desc = (attrib.get("content-desc") or "").strip()
            res_id = (attrib.get("resource-id") or "").strip()
            clickable = attrib.get("clickable") == "true"
            editable = (
                attrib.get("class", "").endswith("EditText")
                or attrib.get("focusable") == "true"
                and attrib.get("class", "").endswith("EditText")
            )

            # Bilkul khali nodes skip karo — kachra hai
            if not text and not desc and not res_id and not clickable:
                continue

            elements.append(
                UIElement(
                    text=text,
                    content_desc=desc,
                    resource_id=res_id,
                    class_name=attrib.get("class", ""),
                    clickable=clickable,
                    editable=editable,
                    enabled=attrib.get("enabled", "true") == "true",
                    bounds=_parse_bounds(attrib.get("bounds", "")),
                )
            )

        return elements

    # ------------------------------------------------------------------
    #  App management
    # ------------------------------------------------------------------

    async def launch_app(self, app: str) -> ActionResult:
        """
        App kholo. App ka aam naam ya package name — dono chalega.

        Hinglish lexicon se package resolve hota hai, isliye
        "paytm kholo" seedha kaam karta hai.
        """
        from ..lang.lexicon import resolve_app

        package = app if "." in app else (resolve_app(app) or app)

        result = await self._shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
            timeout=30.0,
        )

        # monkey fail ho to error usually output mein hota hai
        if not result.ok or "No activities found" in result.output:
            return ActionResult.failure(
                f"'{app}' nahi khul paya (package: {package}). "
                f"App installed hai? list_apps se check kar."
            )

        # App ko load hone ka time do
        await asyncio.sleep(1.5)
        return ActionResult.success(f"{app} khol diya", package=package)

    async def close_app(self, app: str) -> ActionResult:
        from ..lang.lexicon import resolve_app

        package = app if "." in app else (resolve_app(app) or app)
        result = await self._shell(f"am force-stop {package}")
        if result.ok:
            return ActionResult.success(f"{app} band kar diya", package=package)
        return result

    async def list_apps(self, only_user_apps: bool = True) -> ActionResult:
        """Installed apps ki list."""
        flag = "-3" if only_user_apps else ""
        result = await self._shell(f"pm list packages {flag}".strip(), timeout=45.0)
        if not result.ok:
            return result

        packages = [
            line.replace("package:", "").strip()
            for line in result.output.splitlines()
            if line.startswith("package:")
        ]
        packages.sort()

        return ActionResult.success(
            f"{len(packages)} apps installed hain",
            packages=packages,
        )

    async def current_app(self) -> ActionResult:
        """Abhi kaunsa app khula hai?"""
        result = await self._shell(
            "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'", timeout=15.0
        )
        if not result.ok:
            return result

        match = re.search(r"([a-zA-Z0-9_.]+)/([a-zA-Z0-9_.]+)", result.output)
        if match:
            return ActionResult.success(
                f"Abhi khula hai: {match.group(1)}",
                package=match.group(1),
                activity=match.group(2),
            )
        return ActionResult.success(result.output)

    # ------------------------------------------------------------------
    #  Shell & notifications
    # ------------------------------------------------------------------

    async def run_shell(self, command: str) -> ActionResult:
        return await self._shell(command)

    async def read_notifications(self) -> ActionResult:
        """Notifications padho."""
        result = await self._shell(
            "dumpsys notification --noredact | grep -E 'tickerText|android.title|android.text'",
            timeout=30.0,
        )
        if not result.ok:
            return result

        lines = [ln.strip() for ln in result.output.splitlines() if ln.strip()]
        if not lines:
            return ActionResult.success("Koi notification nahi hai")

        return ActionResult.success(
            f"{len(lines)} notification lines mili:\n" + "\n".join(lines[:40]),
            raw_lines=lines,
        )

    # ------------------------------------------------------------------
    #  Convenience
    # ------------------------------------------------------------------

    async def unlock(self) -> ActionResult:
        """
        Screen jagao. PIN/pattern SAARTHI nahi daalega (security rule),
        wo user khud karega.
        """
        await self.press_key("wake")
        await asyncio.sleep(0.4)
        await self.swipe(500, 1500, 500, 500, 300)
        return ActionResult.success(
            "Screen jaga diya. Agar PIN/pattern hai to tu khud daal de "
            "— main password nahi daalta (security rule)."
        )
