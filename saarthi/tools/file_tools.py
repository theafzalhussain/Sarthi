"""
File Tools — file likhna aur padhna.

⚠️ YE TOOLS EK ASLI FAILURE SE BANE HAIN.

User ne bola "excel par ek student marks sheet bna de". Agent ke paas
file likhne ka KOI TOOL NAHI THA — sirf `command_chalao`. Isliye usne
poora Python script SHELL COMMAND ke andar ghusane ki koshish ki:

    powershell -Command "@'\\nimport openpyxl\\n...'@ > file.py"
    cmd /c "echo import openpyxl > file.py && echo ... >> file.py"
    python -c "open('f.py','w').write('...\\\\n...\\\\\\"...')"

Nested quotes ka narak. 20+ koshish, saari fail:
    FAIL: The string is missing the terminator: '@.
    FAIL: The filename, directory name, or volume label syntax is incorrect.
Aur aakhir mein: "max steps limit".

Ye agent ki galti NAHI thi — TOOL HI NAHI THA. Shell escaping ke through
multi-line code likhna practically impossible hai.

Ab `file_banao` se agent seedha content likhta hai, phir
`command_chalao` se chala leta hai. Ek step, koi escaping nahi.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..devices.base import ActionResult
from .base import Tool, ToolContext
from .safety import check_text_safety

# Ye jagah likhne se mana hai — system tod sakta hai
_BLOCKED_PATH_PARTS = (
    "system32", "/etc/", "/boot/", "/sys/", "/proc/", "/dev/",
    "program files", "windowsapps",
)

# Ye extensions chal jaate hain — inko banane se mana
_EXECUTABLE_SUFFIXES = (
    ".exe", ".dll", ".so", ".dylib", ".msi", ".bat", ".cmd", ".ps1",
    ".vbs", ".scr", ".com",
)

MAX_WRITE_CHARS = 200_000


def _resolve(path_text: str) -> Path:
    """
    Path resolve karo — `~` aur env vars dono.

    LLM dono style likhta hai: `~/Desktop/x.csv` aur
    `%USERPROFILE%\\Desktop\\x.csv`. Dono chalne chahiye.
    """
    expanded = os.path.expandvars(str(path_text).strip().strip('"').strip("'"))
    return Path(expanded).expanduser()


def _path_problem(path: Path) -> str:
    """Yahan likhna safe hai? Problem ho to wajah do."""
    lowered = str(path).lower()

    for blocked in _BLOCKED_PATH_PARTS:
        if blocked in lowered:
            return (
                f"'{path}' system ki jagah hai — wahan likhna mana hai. "
                f"Desktop ya Documents mein likh."
            )

    if path.suffix.lower() in _EXECUTABLE_SUFFIXES:
        return (
            f"'{path.suffix}' file chal jaati hai — main aisi file nahi "
            f"banaunga. Ye security rule hai, negotiable nahi."
        )

    return ""


class WriteFileTool(Tool):
    """File banao ya usme likho."""

    name = "file_banao"
    description = (
        "File banao ya usme likho. Multi-line content bilkul theek hai — "
        "koi escaping nahi karni. "
        "YE USE KAR jab bhi koi file banani ho: Python script, CSV, text "
        "note, JSON, HTML. Shell command (echo/powershell) se file likhne "
        "ki koshish MAT kar — nested quotes se wo fail hota hai. "
        "Script bana ke chalana ho to: pehle file_banao, phir "
        "command_chalao se 'python <path>'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File ka path, jaise '~/Desktop/marks.csv'. "
                    "Folder na ho to ban jaayega."
                ),
            },
            "content": {
                "type": "string",
                "description": "File mein kya likhna hai (multi-line theek hai)",
            },
            "append": {
                "type": "boolean",
                "description": "True = end mein jodo, False = overwrite (default)",
            },
        },
        "required": ["path", "content"],
    }
    risky = True  # File ban rahi hai — user ko pata hona chahiye

    async def run(
        self, ctx: ToolContext, path: str, content: str, append: bool = False
    ) -> ActionResult:
        target = _resolve(path)

        problem = _path_problem(target)
        if problem:
            return ActionResult.failure(problem)

        text = "" if content is None else str(content)
        if len(text) > MAX_WRITE_CHARS:
            return ActionResult.failure(
                f"Content bahut bada hai ({len(text)} chars, max "
                f"{MAX_WRITE_CHARS}). Chhote hisson mein likh (append=true)."
            )

        # Safety layer — password/OTP file mein bhi nahi jaane chahiye
        assessment = check_text_safety(text)
        if assessment.is_blocked:
            return ActionResult.failure(assessment.reason)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a" if append else "w", encoding="utf-8") as handle:
                handle.write(text)
        except PermissionError:
            return ActionResult.failure(
                f"'{target}' pe likhne ki permission nahi hai. "
                f"File kisi app mein khuli ho to band kar."
            )
        except OSError as exc:
            return ActionResult.failure(f"File likhi nahi ja saki: {exc}")

        try:
            size = target.stat().st_size
        except OSError:
            size = len(text.encode("utf-8"))

        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        action = "jod diya" if append else "bana diya"

        return ActionResult.success(
            f"File {action}: {target}\n  {lines} lines, {size} bytes",
            path=str(target),
            size=size,
            lines=lines,
        )


class ReadFileTool(Tool):
    """File padho."""

    name = "file_padho"
    description = (
        "Kisi file ka content padho. Tab use kar jab file banane ke baad "
        "verify karna ho, ya user ki file dekhni ho (CSV, text, code, log)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File ka path"},
            "max_chars": {
                "type": "integer",
                "description": "Max kitna text (default 4000)",
            },
        },
        "required": ["path"],
    }

    async def run(
        self, ctx: ToolContext, path: str, max_chars: int = 4000
    ) -> ActionResult:
        target = _resolve(path)
        max_chars = max(200, min(int(max_chars), 40_000))

        if not target.exists():
            return ActionResult.failure(f"File nahi mili: {target}")

        if target.is_dir():
            try:
                items = sorted(p.name for p in target.iterdir())[:60]
            except OSError as exc:
                return ActionResult.failure(f"Folder padha nahi ja saka: {exc}")
            return ActionResult.success(
                f"'{target}' ek FOLDER hai. Andar {len(items)} cheezein:\n  "
                + "\n  ".join(items)
            )

        try:
            raw = target.read_bytes()
        except PermissionError:
            return ActionResult.failure(f"'{target}' padhne ki permission nahi hai")
        except OSError as exc:
            return ActionResult.failure(f"File padhi nahi ja saki: {exc}")

        # Binary (xlsx, png)? Text ki tarah dikhana bekaar hai
        if b"\x00" in raw[:4096]:
            return ActionResult.failure(
                f"'{target.name}' binary file hai ({len(raw)} bytes) — text "
                f"ki tarah nahi padh sakta. Excel/PDF ka content chahiye to "
                f"script likh ke padho."
            )

        text = raw.decode("utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n... (aur bhi hai)"

        return ActionResult.success(
            f"[{target}]  {len(raw)} bytes\n\n{text}",
            path=str(target),
            truncated=truncated,
        )


class ListFilesTool(Tool):
    """Folder mein kya hai."""

    name = "files_dikhao"
    description = (
        "Folder ka content dikhao. Tab use kar jab dhoondhna ho ki file "
        "kahan hai, ya banayi hui file sach mein bani ya nahi."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Folder ka path (default: home folder)",
            },
            "pattern": {
                "type": "string",
                "description": "Filter, jaise '*.csv' ya '*marks*'",
            },
        },
        "required": [],
    }

    async def run(
        self, ctx: ToolContext, path: str = "~", pattern: str = "*"
    ) -> ActionResult:
        target = _resolve(path or "~")

        if not target.exists():
            return ActionResult.failure(f"Folder nahi mila: {target}")
        if not target.is_dir():
            return ActionResult.failure(f"'{target}' folder nahi hai, file hai")

        try:
            matches = sorted(target.glob(pattern or "*"))[:80]
        except OSError as exc:
            return ActionResult.failure(f"Folder padha nahi ja saka: {exc}")

        if not matches:
            return ActionResult.success(
                f"'{target}' mein '{pattern}' se kuch match nahi hua"
            )

        lines = [f"'{target}' mein {len(matches)} cheezein:"]
        for item in matches:
            try:
                if item.is_dir():
                    lines.append(f"  [folder] {item.name}")
                else:
                    lines.append(f"  {item.name}  ({item.stat().st_size} bytes)")
            except OSError:
                lines.append(f"  {item.name}")

        return ActionResult.success("\n".join(lines), count=len(matches))





# ======================================================================
#  PYTHON EXECUTION — agent ka sabse taakatwar tool
#
#  KYUN YE ZAROORI HAI:
#
#  `command_chalao` shell ke through chalta hai, aur shell mein
#  multi-line code likhna narak hai (BUG#15 dekh). `file_banao` +
#  `command_chalao` se kaam ho jaata hai, par wo DO step hain aur
#  agent ko path yaad rakhna padta hai.
#
#  `python_chalao` se ek step mein kaam ho jaata hai. Aur isse agent
#  ki taakat bahut badh jaati hai:
#      Excel/CSV banana aur padhna (openpyxl, csv)
#      JSON/data processing
#      Complex maths
#      Files ko bulk mein rename/organize karna
#      Text processing, regex
#      Jo bhi library user ke paas installed hai
#
#  SAFETY: `command_chalao` ke SAME gate se guzarta hai (risky=True ->
#  confirmation). Naya risk nahi hai — agent pehle se shell chala sakta
#  tha. Par Python-specific destructive patterns ka extra check hai.
# ======================================================================

# Python code mein ye patterns milne pe MANA. Ye hard block hai —
# `command_chalao` ke BLOCKED_SHELL jaisa, par Python ke liye.
_BLOCKED_CODE_PATTERNS: tuple = (
    # Pura filesystem uda dena
    (r"shutil\s*\.\s*rmtree\s*\(\s*['\"]?[/\\]['\"]?\s*\)", "pura root delete kar raha hai"),
    (r"shutil\s*\.\s*rmtree\s*\(\s*['\"](?:C:)?[/\\](?:Windows|Users|etc|home)",
     "system folder delete kar raha hai"),
    # Shell ke through destructive kaam (Python se bypass ki koshish)
    (r"(?:os\s*\.\s*system|subprocess\s*\.\s*\w+)\s*\([^)]*rm\s+-rf\s+/", "rm -rf / chala raha hai"),
    (r"(?:os\s*\.\s*system|subprocess\s*\.\s*\w+)\s*\([^)]*mkfs", "disk format kar raha hai"),
    (r"(?:os\s*\.\s*system|subprocess\s*\.\s*\w+)\s*\([^)]*(?:shutdown|reboot)\b",
     "system band kar raha hai"),
    # Raw disk pe likhna
    (r"open\s*\(\s*['\"]/dev/[sh]d", "direct disk pe likh raha hai"),
    # Fork bomb
    (r"while\s+True\s*:.*os\s*\.\s*fork", "fork bomb hai"),
)

MAX_CODE_CHARS = 100_000


def check_python_safety(code: str) -> str:
    """
    Python code safe hai? Problem ho to wajah return karo, warna "".

    Ye `safety.py` ke `check_shell_safety()` ka Python version hai.
    Design principle wahi: FAIL SAFE, doubt ho to mana kar do.
    """
    import re

    text = str(code or "")

    for pattern, reason in _BLOCKED_CODE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return reason

    # Password/OTP check — code mein bhi nahi likhna chahiye
    assessment = check_text_safety(text)
    if assessment.is_blocked:
        return assessment.reason

    return ""


class RunPythonTool(Tool):
    """Python code chalao."""

    name = "python_chalao"
    description = (
        "Python code chalao. YE TERA SABSE TAAKATWAR TOOL HAI — jab bhi "
        "kuch complex karna ho to shell ke jugaad ke bajaay YE use kar.\n"
        "Ismein kya kar sakta hai:\n"
        "  Excel/CSV banana aur padhna (openpyxl, csv, pandas)\n"
        "  JSON/data processing, complex maths\n"
        "  Bahut si files rename/organize karna\n"
        "  Text processing, regex\n"
        "Multi-line code SEEDHA likh — koi escaping nahi, koi quote ki "
        "tension nahi. Result dekhne ke liye print() use kar.\n"
        "Library na ho to pehle command_chalao se "
        "'pip install <naam>' chala le."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python code (multi-line theek hai). Output ke liye "
                    "print() use kar."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Max kitne second (default 60, max 300)",
            },
        },
        "required": ["code"],
    }
    risky = True  # Code chal raha hai — user ko pata hona chahiye

    async def run(
        self, ctx: ToolContext, code: str, timeout: int = 60
    ) -> ActionResult:
        import asyncio
        import sys
        import tempfile

        text = str(code or "")
        if not text.strip():
            return ActionResult.failure("Code khali hai")

        if len(text) > MAX_CODE_CHARS:
            return ActionResult.failure(
                f"Code bahut bada hai ({len(text)} chars, max {MAX_CODE_CHARS})"
            )

        # SAFETY: hard blocks pehle
        problem = check_python_safety(text)
        if problem:
            return ActionResult.failure(
                f"Ye code block hai: {problem}. Main ye nahi chalaunga."
            )

        timeout = max(5, min(int(timeout or 60), 300))

        # Temp file mein likh ke chalao.
        #
        # `python -c` se nahi chala rahe kyunki wahan multi-line code ka
        # wahi quoting problem aa jaata hai jo BUG#15 mein tha.
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False
        )
        script_path = handle.name
        try:
            handle.write(text)
            handle.close()

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:  # noqa: BLE001
                    pass
                return ActionResult.failure(
                    f"Code {timeout} second mein khatam nahi hua — "
                    f"infinite loop ho sakta hai"
                )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Code chal nahi paya: {exc}")
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        exit_code = process.returncode or 0

        # Lamba output LLM ke tokens kha jaayega
        if len(out) > 4000:
            out = out[:4000] + f"\n... (aur {len(out) - 4000} characters)"
        if len(err) > 2000:
            err = err[:2000] + "\n... (aur bhi)"

        if exit_code != 0:
            # Error mein sabse kaam ki line aakhri hoti hai
            return ActionResult.failure(
                f"Code error de gaya (exit {exit_code}):\n{err or out or '(kuch nahi)'}",
                exit_code=exit_code,
                stdout=out,
                stderr=err,
            )

        message = out or "(code chal gaya, koi output nahi — print() lagana bhool gaya?)"
        if err:
            message += f"\n\n[warnings]\n{err}"

        return ActionResult.success(message, exit_code=0, stdout=out, stderr=err)


class OpenFileTool(Tool):
    """File ya folder user ke liye khol do."""

    name = "file_kholo"
    description = (
        "File ya folder USER KE LIYE khol do — default app mein "
        "(Excel .xlsx ke liye, Notepad .txt ke liye, File Explorer folder "
        "ke liye). "
        "Ye tab use kar jab user bole 'file do mujhe' / 'dikha do' / "
        "'khol do', ya jab tu koi file bana chuka ho aur user ko dena ho. "
        "File banane ke baad ye karna acchi baat hai — user ko dhoondhna "
        "nahi padta."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File ya folder ka path",
            },
        },
        "required": ["path"],
    }

    async def run(self, ctx: ToolContext, path: str) -> ActionResult:
        import asyncio
        import subprocess
        import sys

        target = _resolve(path)

        if not target.exists():
            return ActionResult.failure(
                f"'{target}' nahi mili. files_dikhao se check kar ki file kahan hai."
            )

        try:
            if sys.platform.startswith("win"):
                # os.startfile Windows pe default app se kholta hai
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                await asyncio.create_subprocess_exec("open", str(target))
            else:
                await asyncio.create_subprocess_exec(
                    "xdg-open", str(target),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        except FileNotFoundError:
            return ActionResult.failure(
                f"File kholne wala command nahi mila is system pe. "
                f"Khud khol le: {target}"
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(
                f"'{target}' khul nahi payi: {exc}\nKhud khol le: {target}"
            )

        kind = "Folder" if target.is_dir() else "File"
        return ActionResult.success(
            f"{kind} khol di: {target}\n  (default app mein khuli hai)",
            path=str(target),
        )


def file_tools() -> list[Tool]:
    """Saare file tools."""
    return [
        WriteFileTool(),
        ReadFileTool(),
        ListFilesTool(),
        RunPythonTool(),
        OpenFileTool(),
    ]
