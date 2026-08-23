"""
Desktop/Laptop Device Adapter.

Wahi interface jo Android ka hai — par yahan shell, files aur
(optional) mouse/keyboard control milta hai.

Design: agar `pyautogui` install nahi hai to bhi crash nahi hoga.
Shell aur files ka kaam chalta rahega, sirf mouse/keyboard skip honge.
Isse ₹0 setup pe bhi turant kaam shuru ho jaata hai.

Mouse/keyboard chahiye to:
    pip install pyautogui
"""

from __future__ import annotations

import asyncio
import base64
import os
import platform
import shutil
import sys
from pathlib import Path

from .base import ActionResult, Capability, Device

# ----------------------------------------------------------------------
#  Optional GUI control — na ho to bhi chalega
# ----------------------------------------------------------------------

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    HAS_GUI = True
except Exception:  # noqa: BLE001 — headless server pe import bhi fail hota hai
    pyautogui = None  # type: ignore[assignment]
    HAS_GUI = False


# Khatarnak shell commands — inko block karte hain.
# Ye defence-in-depth hai: LLM galti kare to bhi system safe rahe.
DANGEROUS_PATTERNS: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    ":(){:|:&};:",       # fork bomb
    "> /dev/sda",
    "chmod -R 000 /",
    "shutdown",
    "reboot",
    "init 0",
    "halt",
    "format c:",
    "del /f /s /q c:\\",
)


def _is_dangerous(command: str) -> str | None:
    """Command khatarnak hai? Wajah return karo, warna None."""
    normalized = " ".join(command.lower().split())
    for pattern in DANGEROUS_PATTERNS:
        if pattern in normalized:
            return pattern
    return None


class DesktopDevice(Device):
    """Local computer — jahan SAARTHI khud chal raha hai."""

    kind = "desktop"

    def __init__(self, name: str = "desktop", allow_shell: bool = True):
        super().__init__(name)
        self.allow_shell = allow_shell

        caps = {
            Capability.FILES,
            Capability.DEVICE_INFO,
            Capability.LAUNCH_APP,
        }
        if allow_shell:
            caps.add(Capability.SHELL)
        if HAS_GUI:
            caps |= {
                Capability.TAP,
                Capability.TYPE,
                Capability.KEY,
                Capability.SCREENSHOT,
                Capability.SWIPE,
            }
        self.capabilities = caps

    # ------------------------------------------------------------------
    #  Connection
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Local machine hai — hamesha available."""
        return True

    async def info(self) -> ActionResult:
        details = {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "hostname": platform.node(),
            "gui_control": "haan" if HAS_GUI else "nahi (pip install pyautogui)",
        }

        if HAS_GUI:
            try:
                width, height = pyautogui.size()
                details["screen"] = f"{width}x{height}"
            except Exception:  # noqa: BLE001
                pass

        summary = ", ".join(f"{k}={v}" for k, v in details.items())
        return ActionResult.success(summary, **details)

    # ------------------------------------------------------------------
    #  Shell
    # ------------------------------------------------------------------

    async def run_shell(self, command: str, timeout: float = 60.0) -> ActionResult:
        """Local shell command chalao — safety check ke saath."""
        if not self.allow_shell:
            return ActionResult.failure("Shell access band hai")

        danger = _is_dangerous(command)
        if danger:
            return ActionResult.failure(
                f"Ye command block kar diya — khatarnak pattern mila: '{danger}'. "
                "Aisa kaam main nahi karunga."
            )

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            return ActionResult.failure(f"Command timeout ({timeout}s)")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Command fail: {exc}")

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        code = process.returncode or 0

        # Bahut lamba output LLM ke tokens kha jaayega — kaat do
        if len(out) > 4000:
            out = out[:4000] + f"\n... (aur {len(out) - 4000} characters)"

        if code != 0:
            return ActionResult.failure(
                err or out or f"exit code {code}", exit_code=code
            )

        return ActionResult.success(out or "(koi output nahi)", exit_code=code)

    # ------------------------------------------------------------------
    #  Files
    # ------------------------------------------------------------------

    async def read_file(self, path: str, max_chars: int = 8000) -> ActionResult:
        try:
            file_path = Path(path).expanduser()
            if not file_path.exists():
                return ActionResult.failure(f"File nahi mili: {path}")
            if file_path.is_dir():
                return ActionResult.failure(f"Ye folder hai, file nahi: {path}")

            content = file_path.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > max_chars

            return ActionResult.success(
                content[:max_chars] + ("\n... (aur bhi hai)" if truncated else ""),
                path=str(file_path),
                truncated=truncated,
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"File padh nahi paya: {exc}")

    async def write_file(self, path: str, content: str) -> ActionResult:
        try:
            file_path = Path(path).expanduser()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ActionResult.success(
                f"Likh diya: {file_path} ({len(content)} characters)",
                path=str(file_path),
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"File likh nahi paya: {exc}")

    async def list_dir(self, path: str = ".") -> ActionResult:
        try:
            dir_path = Path(path).expanduser()
            if not dir_path.exists():
                return ActionResult.failure(f"Folder nahi mila: {path}")

            entries = sorted(
                dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
            lines = [
                f"  {'[dir] ' if e.is_dir() else '      '}{e.name}"
                for e in entries[:200]
            ]
            return ActionResult.success(
                f"{dir_path} mein {len(entries)} items:\n" + "\n".join(lines),
                count=len(entries),
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Folder padh nahi paya: {exc}")

    # ------------------------------------------------------------------
    #  App launching
    # ------------------------------------------------------------------

    async def launch_app(self, app: str) -> ActionResult:
        """OS ke hisaab se app kholo."""
        system = platform.system()

        if system == "Darwin":
            command = f'open -a "{app}"'
        elif system == "Windows":
            command = f'start "" "{app}"'
        else:  # Linux
            if shutil.which(app.split()[0]):
                command = f"nohup {app} >/dev/null 2>&1 &"
            elif shutil.which("xdg-open"):
                command = f'xdg-open "{app}"'
            else:
                return ActionResult.failure(
                    f"'{app}' launch nahi kar paya — command nahi mila"
                )

        result = await self.run_shell(command, timeout=15.0)
        if result.ok:
            return ActionResult.success(f"{app} khol diya")
        return result

    # ------------------------------------------------------------------
    #  GUI control (pyautogui chahiye)
    # ------------------------------------------------------------------

    def _need_gui(self) -> ActionResult:
        return ActionResult.failure(
            "GUI control available nahi hai. Chahiye to: pip install pyautogui\n"
            "(Headless server pe ye kaam nahi karega — display chahiye.)"
        )

    async def tap(self, x: int, y: int) -> ActionResult:
        if not HAS_GUI:
            return self._need_gui()
        try:
            pyautogui.click(x=int(x), y=int(y))
            return ActionResult.success(f"click kiya ({x},{y})")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Click fail: {exc}")

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> ActionResult:
        if not HAS_GUI:
            return self._need_gui()
        try:
            pyautogui.moveTo(int(x1), int(y1))
            pyautogui.dragTo(int(x2), int(y2), duration=duration_ms / 1000.0)
            return ActionResult.success(f"drag kiya ({x1},{y1}) -> ({x2},{y2})")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Drag fail: {exc}")

    async def type_text(self, text: str) -> ActionResult:
        if not HAS_GUI:
            return self._need_gui()
        try:
            pyautogui.typewrite(text, interval=0.01)
            return ActionResult.success(f"type kiya: {text[:60]}")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Type fail: {exc}")

    async def press_key(self, key: str) -> ActionResult:
        if not HAS_GUI:
            return self._need_gui()
        try:
            # "ctrl+c" jaise combos handle karo
            if "+" in key:
                pyautogui.hotkey(*[k.strip() for k in key.split("+")])
            else:
                pyautogui.press(key.strip())
            return ActionResult.success(f"{key} press kiya")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Key press fail: {exc}")

    async def screenshot(self) -> ActionResult:
        """Screenshot lo — pyautogui se, ya Linux tools se fallback."""
        if HAS_GUI:
            try:
                import io

                image = pyautogui.screenshot()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                raw = buffer.getvalue()
                return ActionResult.success(
                    f"Screenshot liya ({len(raw) // 1024} KB)",
                    image_b64=base64.b64encode(raw).decode("ascii"),
                    image_mime="image/png",
                )
            except Exception as exc:  # noqa: BLE001
                return ActionResult.failure(f"Screenshot fail: {exc}")

        # Linux fallback — koi bhi available tool try karo
        for tool, command in (
            ("gnome-screenshot", "gnome-screenshot -f {path}"),
            ("scrot", "scrot {path}"),
            ("import", "import -window root {path}"),
            ("spectacle", "spectacle -b -n -o {path}"),
        ):
            if not shutil.which(tool):
                continue

            temp_path = Path(os.environ.get("TMPDIR", "/tmp")) / "saarthi_shot.png"
            result = await self.run_shell(
                command.format(path=temp_path), timeout=20.0
            )
            if result.ok and temp_path.exists():
                raw = temp_path.read_bytes()
                temp_path.unlink(missing_ok=True)
                return ActionResult.success(
                    f"Screenshot liya ({len(raw) // 1024} KB, {tool} se)",
                    image_b64=base64.b64encode(raw).decode("ascii"),
                    image_mime="image/png",
                )

        return self._need_gui()
