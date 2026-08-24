"""
SAARTHI — Terminal UI layer.

Ek hi jagah se pura look. `cli.py` aur `voice_cli.py` dono isi ko use
karte hain, isliye dono bilkul ek jaise dikhte hain. Naya entrypoint
banega (server, TUI) to wo bhi yahi use karega.

DESIGN KE RULES (inko follow karna, warna look bikhar jaayega):

  1. Rang KAM, structure ZYADA
     Professional cheezein rainbow nahi hoti. Ek brand color (sky blue),
     ek accent, aur baaki gray ke shades. Bas.

  2. 80 COLUMN mein fit hona chahiye
     Purana laptop, chhoti terminal window, SSH — sab pe theek dikhe.
     Ye Pillar #3 (budget hardware) ka UI wala hissa hai.

  3. rich na ho to CRASH nahi
     Project ka rule hai: optional dependency degrade karti hai.
     rich missing ho to plain ANSI colors pe chala jaata hai.

  4. Unicode na chale to ASCII
     Windows ka purana terminal UTF-8 nahi handle karta. Isliye har
     fancy character ka ek ASCII fallback hai.

  5. Hinglish personality BANI RAHEGI
     Look professional hoga, baat dosti wali. Ye contradiction nahi hai —
     Swiggy ka app professional dikhta hai par "Kya khaana hai?" puchta hai.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Iterable, Optional, Sequence

# ----------------------------------------------------------------------
#  Optional dependency: rich
# ----------------------------------------------------------------------

try:
    from rich import box
    from rich.console import Console, Group
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    HAS_RICH = True
except ImportError:  # pragma: no cover — rich requirements mein hai
    HAS_RICH = False
    box = None  # type: ignore[assignment]
    Console = None  # type: ignore[assignment]
    Group = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]


# ======================================================================
#  PALETTE
#
#  Sky-blue brand + slate grays. Ye combination "official tool" jaisa
#  lagta hai (socho: Vercel, Linear, Stripe ke CLIs).
#
#  Hex use kar rahe hain — modern terminals truecolor support karte hain,
#  aur purane terminals pe rich khud nearest color pe map kar deta hai.
# ======================================================================

BRAND = "#38bdf8"       # sky-400   — logo, headings, prompt
BRAND_DEEP = "#0284c7"  # sky-600   — gradient ka neeche wala hissa
ACCENT = "#a78bfa"       # violet-400 — tool activity
OK = "#4ade80"           # green-400 — success, connected
WARN = "#fbbf24"         # amber-400 — dhyan dene wali baat
ERR = "#f87171"          # red-400   — error
TEXT = "#e2e8f0"         # slate-200 — normal text
MUTED = "#64748b"        # slate-500 — dim/secondary
HEAD = "#94a3b8"         # slate-400 — table headers


# Plain ANSI fallback (rich na ho to)
_ANSI = {
    BRAND: "\033[96m",
    BRAND_DEEP: "\033[36m",
    ACCENT: "\033[95m",
    OK: "\033[92m",
    WARN: "\033[93m",
    ERR: "\033[91m",
    TEXT: "\033[0m",
    MUTED: "\033[90m",
    HEAD: "\033[90m",
    "bold": "\033[1m",
}
_RESET = "\033[0m"


# ======================================================================
#  WORDMARK
# ======================================================================

# ANSI-Shadow style. Width = 52 columns, isliye 80-col terminal mein
# comfortably fit ho jaata hai.
_WORDMARK = [
    "███████╗ █████╗  █████╗ ██████╗ ████████╗██╗  ██╗██╗",
    "██╔════╝██╔══██╗██╔══██╗██╔══██╗╚══██╔══╝██║  ██║██║",
    "███████╗███████║███████║██████╔╝   ██║   ███████║██║",
    "╚════██║██╔══██║██╔══██║██╔══██╗   ██║   ██╔══██║██║",
    "███████║██║  ██║██║  ██║██║  ██║   ██║   ██║  ██║██║",
    "╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝",
]

# Upar se neeche halka -> gehra. Isse logo mein depth aata hai.
_WORDMARK_GRADIENT = [
    "#7dd3fc", "#38bdf8", "#0ea5e9", "#0284c7", "#0369a1", "#075985",
]

# Chhoti terminal ya no-unicode ke liye
_WORDMARK_SMALL = "S A A R T H I"


# ======================================================================
#  SYMBOLS — har ek ka ASCII fallback
# ======================================================================

_SYMBOLS_UNICODE = {
    "on": "●",         # connected / available
    "off": "○",        # not connected
    "prompt": "❯",     # input prompt
    "run": "▸",        # tool chal raha hai
    "ok": "✓",
    "fail": "✗",
    "think": "⋯",
    "warn": "!",
    "bullet": "·",
    "arrow": "→",
    "gutter": "│",
    "corner": "╰",
    "mic": "◉",
}

_SYMBOLS_ASCII = {
    "on": "*",
    "off": "-",
    "prompt": ">",
    "run": ">",
    "ok": "+",
    "fail": "x",
    "think": "...",
    "warn": "!",
    "bullet": "-",
    "arrow": "->",
    "gutter": "|",
    "corner": "+",
    "mic": "o",
}


def _supports_unicode() -> bool:
    """Terminal fancy characters dikha sakta hai?"""
    if os.getenv("SAARTHI_ASCII_UI"):
        return False
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def terminal_width(default: int = 80) -> int:
    """Terminal ki chaudai. Pata na chale to 80 maan lo."""
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:  # noqa: BLE001
        return default


# ======================================================================
#  UI
# ======================================================================


class Ui:
    """
    SAARTHI ka terminal renderer.

    Use:
        ui = Ui()
        ui.banner("0.2.0")
        ui.section("BRAIN")
        ui.info("kuch baat")
    """

    def __init__(self, plain: Optional[bool] = None):
        """
        Args:
            plain: True = rich use na karo (testing/piping ke liye).
                   None = khud decide karo.
        """
        force_plain = bool(os.getenv("SAARTHI_PLAIN_UI"))
        self.rich = HAS_RICH and not force_plain and (plain is not True)

        self.console = Console(highlight=False, soft_wrap=False) if self.rich else None
        self.unicode = _supports_unicode()
        self.sym = _SYMBOLS_UNICODE if self.unicode else _SYMBOLS_ASCII

        # Content ki max width — 80-col pe fit, bade screen pe bhi
        # padhne mein aasaan (lambi lines aankh thaka deti hain)
        self.width = min(terminal_width(), 84)

    # ------------------------------------------------------------------
    #  Primitives
    # ------------------------------------------------------------------

    def raw(self, renderable) -> None:
        """Rich object ya plain string — jo mile print kar do."""
        if self.rich and self.console is not None:
            self.console.print(renderable)
        else:
            print(renderable)

    def blank(self, count: int = 1) -> None:
        """Khali line."""
        for _ in range(count):
            print()

    def line(self, text: str = "", color: str = TEXT, bold: bool = False) -> None:
        """Ek line, rang ke saath."""
        if self.rich and self.console is not None:
            style = color + (" bold" if bold else "")
            self.console.print(Text(text, style=style))
            return

        prefix = _ANSI.get(color, "")
        if bold:
            prefix = _ANSI["bold"] + prefix
        print(f"{prefix}{text}{_RESET}" if prefix else text)

    def paint(self, text: str, color: str = TEXT, bold: bool = False) -> str:
        """
        Rang lagaya hua string WAPAS do (print nahi karo).

        Ye `input()` ke prompt ke liye chahiye — usko rich se nahi,
        plain ANSI string se hi dena padta hai.
        """
        prefix = _ANSI.get(color, "")
        if bold:
            prefix = _ANSI["bold"] + prefix
        return f"{prefix}{text}{_RESET}" if prefix else text

    # ------------------------------------------------------------------
    #  Structure
    # ------------------------------------------------------------------

    def section(self, title: str, color: str = HEAD) -> None:
        """
        Section heading — ek dim rule ke saath.

            BRAIN ─────────────────────────────────────────
        """
        label = title.strip().upper()

        if self.rich and self.console is not None:
            dash = "─" if self.unicode else "-"
            fill = max(0, self.width - len(label) - 4)
            body = Text()
            body.append("  ")
            body.append(label, style=color + " bold")
            body.append(" " + dash * fill, style=MUTED)
            self.console.print(body)
            return

        dash = "-"
        fill = max(0, self.width - len(label) - 4)
        self.line(f"  {label} {dash * fill}", color, bold=True)

    def rule(self) -> None:
        """Simple divider."""
        dash = "─" if self.unicode else "-"
        self.line("  " + dash * max(0, self.width - 4), MUTED)

    # ------------------------------------------------------------------
    #  Messages
    # ------------------------------------------------------------------

    def info(self, text: str) -> None:
        self.line(f"  {text}", TEXT)

    def muted(self, text: str) -> None:
        self.line(f"  {text}", MUTED)

    def success(self, text: str) -> None:
        self.line(f"  {self.sym['ok']}  {text}", OK)

    def warn(self, text: str) -> None:
        self.line(f"  {self.sym['warn']}  {text}", WARN)

    def error(self, text: str) -> None:
        self.line(f"  {self.sym['fail']}  {text}", ERR)

    def hint(self, text: str, title: str = "dhyan de") -> None:
        """
        Madad wali baat — box mein, taaki alag dikhe.

        Setup instructions, "ye missing hai" type messages ke liye.
        """
        if self.rich and self.console is not None and Panel is not None:
            self.console.print(
                Panel(
                    Text(text, style=TEXT),
                    title=f"[{WARN} bold]{title}[/]",
                    title_align="left",
                    border_style=WARN,
                    box=box.ROUNDED,
                    padding=(0, 1),
                    width=self.width,
                )
            )
            return

        self.blank()
        self.line(f"  [{title}]", WARN, bold=True)
        for raw_line in text.splitlines():
            self.line(f"  | {raw_line}", WARN)
        self.blank()

    def block(self, text: str, color: str = MUTED, indent: int = 2) -> None:
        """Multi-line text ko indent ke saath dikhao."""
        pad = " " * indent
        for raw_line in text.splitlines():
            self.line(f"{pad}{raw_line}", color)

    # ------------------------------------------------------------------
    #  Banner
    # ------------------------------------------------------------------

    def banner(self, version: str, tagline: str = "", mode: str = "") -> None:
        """
        Startup wordmark.

        Chhoti terminal ya no-unicode ho to chhota version dikhata hai —
        toota-foota ASCII art se accha hai ki saaf text ho.
        """
        self.blank()

        big = self.unicode and terminal_width() >= 56

        if big:
            if self.rich and self.console is not None:
                for row, color in zip(_WORDMARK, _WORDMARK_GRADIENT):
                    self.console.print(Text("  " + row, style=color))
            else:
                for row in _WORDMARK:
                    self.line("  " + row, BRAND)
        else:
            self.line("  " + _WORDMARK_SMALL, BRAND, bold=True)

        # Tagline strip
        bits = []
        if tagline:
            bits.append(tagline)
        bits.append(f"v{version}")
        if mode:
            bits.append(mode)

        sep = f"  {self.sym['bullet']}  "
        self.blank()
        self.line("  " + sep.join(bits), MUTED)
        self.blank()

    # ------------------------------------------------------------------
    #  Tables
    # ------------------------------------------------------------------

    def _new_table(self, headers: Sequence[str]) -> "Table":
        """Theme ke hisaab se khali table."""
        table = Table(
            box=box.SIMPLE_HEAD,
            show_edge=False,
            pad_edge=False,
            header_style=HEAD + " bold",
            border_style=MUTED,
            padding=(0, 1),
        )
        for header in headers:
            table.add_column(header, overflow="fold")
        return table

    def table(
        self,
        headers: Sequence[str],
        rows: Iterable[Sequence[str]],
        indent: int = 2,
    ) -> None:
        """
        Table dikhao. rich na ho to aligned plain text.

        rows ke andar rich markup chal jaayega ("[green]OK[/]").
        """
        rows = [list(r) for r in rows]

        if self.rich and self.console is not None:
            table = self._new_table(headers)
            for row in rows:
                table.add_row(*[str(c) for c in row])
            from rich.padding import Padding

            self.console.print(Padding(table, (0, 0, 0, indent)))
            return

        # --- Plain fallback: khud align karo ---
        import re

        def strip_markup(value: str) -> str:
            return re.sub(r"\[/?[^\]]*\]", "", str(value))

        clean_rows = [[strip_markup(c) for c in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in clean_rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(cell))

        pad = " " * indent
        header_line = "  ".join(
            h.upper().ljust(widths[i]) for i, h in enumerate(headers)
        )
        self.line(pad + header_line, HEAD, bold=True)
        self.line(pad + "  ".join("-" * w for w in widths), MUTED)
        for row in clean_rows:
            self.line(
                pad
                + "  ".join(
                    cell.ljust(widths[i]) if i < len(widths) else cell
                    for i, cell in enumerate(row)
                ),
                TEXT,
            )

    def badge(self, on: bool) -> str:
        """Connected/available ka nishaan (rich markup ke saath)."""
        if on:
            return f"[{OK}]{self.sym['on']}[/]"
        return f"[{MUTED}]{self.sym['off']}[/]"

    # ------------------------------------------------------------------
    #  Agent conversation
    # ------------------------------------------------------------------

    def prompt(self, label: str = "tu") -> str:
        """
        `input()` ko dene wala prompt string.

            tu ❯
        """
        return (
            "  "
            + self.paint(label, BRAND, bold=True)
            + " "
            + self.paint(self.sym["prompt"], BRAND)
            + " "
        )

    def activity(self, kind: str, text: str) -> None:
        """
        Agent live kya kar raha hai.

        Gutter style rakha hai — reply se visually alag dikhta hai,
        aur scroll karte waqt aankh ko follow karna aasaan hota hai.
        """
        if not text:
            return

        gutter = self.sym["gutter"]

        styles = {
            "thinking": (self.sym["think"], MUTED),
            "tool": (self.sym["run"], ACCENT),
            "result": (self.sym["ok"], MUTED),
            "error": (self.sym["fail"], ERR),
            "debug": (self.sym["bullet"], MUTED),
        }
        mark, color = styles.get(kind, (self.sym["bullet"], MUTED))

        for i, raw_line in enumerate(text.splitlines()):
            prefix = f"  {gutter} {mark} " if i == 0 else f"  {gutter}   "
            self.line(f"{prefix}{raw_line}", color)

    def reply(self, text: str, meta: str = "", markdown: bool = True) -> None:
        """
        Agent ka final jawab.

        Panel mein rakha hai — isse jawab tool-noise se saaf alag
        dikhta hai. Ye sabse zyada padha jaane wala hissa hai, isliye
        isko sabse saaf rakha.
        """
        if self.rich and self.console is not None and Panel is not None:
            body = Markdown(text) if (markdown and Markdown) else Text(text, style=TEXT)

            if meta:
                # Meta line ko halka separate karo — warna jawab ka
                # hissa lagta hai
                dash = "─" if self.unicode else "-"
                body = Group(
                    body,
                    Text(dash * max(0, self.width - 4), style=MUTED),
                    Text(meta, style=MUTED),
                )

            self.console.print(
                Panel(
                    body,
                    title=f"[{BRAND} bold]saarthi[/]",
                    title_align="left",
                    border_style=MUTED,
                    box=box.ROUNDED,
                    padding=(0, 1),
                    width=self.width,
                )
            )
            return

        self.line(f"  saarthi {self.sym['prompt']}", BRAND, bold=True)
        self.block(text, TEXT, indent=4)
        if meta:
            self.line(f"    {meta}", MUTED)

    # ------------------------------------------------------------------
    #  SAARTHI-specific renderers
    #
    #  Ye jaan-boojh ke DUCK TYPING pe chalte hain — `ui.py` brain ya
    #  devices ko import nahi karta. Isse do fayde hain:
    #    1. Koi circular import nahi
    #    2. Test mein fake object pass kar sakte hain
    # ------------------------------------------------------------------

    def brain_table(self, brain) -> None:
        """
        LLM providers ka table.

        `brain.providers` mein sirf wahi hote hain jinke paas key hai,
        isliye sab "available" hain. Pehla primary, baaki fallback.
        """
        yes = self.sym["ok"]
        no = self.sym["fail"]
        dash = "—" if self.unicode else "-"

        rows = []
        for index, provider in enumerate(brain.providers):
            primary = index == 0
            has_tools = getattr(provider, "supports_tools", True)

            # Tools SAARTHI ke liye zaroori hain — jo model support nahi
            # karta usko saaf highlight karo, warna user sochta rahega
            # "kaam kyun nahi ho raha"
            tools_cell = (
                f"[{OK}]{yes}[/]" if has_tools else f"[{WARN}]{no}[/]"
            )
            vision_cell = (
                f"[{OK}]{yes}[/]" if provider.supports_vision else f"[{MUTED}]{dash}[/]"
            )

            rows.append(
                [
                    self.badge(primary),
                    provider.name,
                    provider.model,
                    "primary" if primary else "fallback",
                    tools_cell,
                    vision_cell,
                ]
            )

        if not rows:
            self.muted("Koi provider nahi — .env mein API key daal.")
            return

        self.table(["", "provider", "model", "role", "tools", "aankh"], rows)

    def devices_table(self, manager, status: dict, detailed: bool = False) -> list:
        """
        Devices ka table.

        Returns:
            Jo devices connected nahi hain unke setup hints — caller
            decide kare dikhane hain ya nahi (startup pe clutter
            nahi chahiye).
        """
        rows = []
        hints = []

        for name, device in manager.devices.items():
            connected = bool(status.get(name, False))
            caps = sorted(c.value for c in device.capabilities)

            if detailed:
                can_do = ", ".join(caps) if caps else "—"
            else:
                can_do = f"{len(caps)} actions" if caps else "—"

            rows.append(
                [
                    self.badge(connected),
                    name,
                    device.kind,
                    "ready" if connected else "not connected",
                    can_do,
                ]
            )

            if not connected:
                hints.append((name, self._device_hint(name, device)))

        self.table(["", "device", "type", "status", "kya kar sakta hai"], rows)
        return hints

    @staticmethod
    def _device_hint(name: str, device) -> str:
        """Device connected nahi hai to kya karna chahiye."""
        # Device khud bata sakta hai? (BrowserDevice batata hai)
        helper = getattr(device, "setup_help", None)
        if callable(helper):
            try:
                return str(helper())
            except Exception:  # noqa: BLE001
                pass

        if name == "android" or device.kind == "android":
            return (
                "Phone connect karne ke liye:\n"
                "  1. Settings > About phone > Build number pe 7 baar tap\n"
                "  2. Settings > Developer options > USB Debugging ON\n"
                "  3. USB laga, phone pe 'Allow' dabao\n"
                "  4. Check kar: adb devices"
            )

        return f"'{name}' abhi available nahi hai."

    def tools_table(self, registry, max_desc: int = 64) -> None:
        """Saare tools — naam aur kaam."""
        rows = []
        # `names` property hai, method nahi — brackets mat lagana
        for name in registry.names:
            tool = registry.get(name)
            description = (getattr(tool, "description", "") or "").strip()
            # Pehla sentence hi kaafi hai — poora description bahut lamba hai
            first = description.split(". ")[0].strip().rstrip(".")
            if len(first) > max_desc:
                first = first[: max_desc - 1].rstrip() + "…"
            rows.append([name, first or "—"])

        self.table(["tool", "kaam"], rows)

    def reply_error(self, text: str) -> None:
        """Jawab ki jagah error aaya."""
        if self.rich and self.console is not None and Panel is not None:
            self.console.print(
                Panel(
                    Text(text, style=TEXT),
                    title=f"[{ERR} bold]problem[/]",
                    title_align="left",
                    border_style=ERR,
                    box=box.ROUNDED,
                    padding=(0, 1),
                    width=self.width,
                )
            )
            return

        self.line(f"  problem {self.sym['prompt']}", ERR, bold=True)
        self.block(text, ERR, indent=4)


# ----------------------------------------------------------------------
#  Shared instance
# ----------------------------------------------------------------------

ui = Ui()
