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


def file_tools() -> list[Tool]:
    """Saare file tools."""
    return [WriteFileTool(), ReadFileTool(), ListFilesTool()]
