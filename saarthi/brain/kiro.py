"""
Kiro provider — subprocess se `kiro-cli` chalata hai.

⚠️ YE BAAKI PROVIDERS SE ALAG HAI.

Groq/NVIDIA/Gemini sab HTTP API hain — ek URL pe POST karo, JSON wapas
milta hai. Kiro aisa NAHI hai.

Kiro ki `ksk_` API key ek OpenAI-style API key NAHI hai. Usse seedha
`/chat/completions` pe call nahi kar sakte. Wo sirf `kiro-cli` ko
HEADLESS (bina interaction) chalane ke liye hai:

    KIRO_API_KEY=ksk_...  kiro-cli chat --no-interactive "prompt"

Isliye ye provider ek SUBPROCESS chalata hai, HTTP nahi. Kiro ke andar
bade models milte hain (Claude Opus 5, GPT-5.6, Qwen3 Coder, etc.) —
isliye ye BADE kaam ke liye best hai: coding, web search, complex
reasoning. Chhoti baat ke liye ye SLOW aur credit-mehenga hai, isliye
SAARTHI ise sirf bade task pe use karta hai (config.py + router mein
escalation logic dekh).

TOOL CALLING:
    Kiro ke apne tools hain (fs_read, execute, etc.) jo SAARTHI ke
    tools (tap_karo, app_kholo) se alag hain. Hum Kiro ko SAARTHI ke
    tools nahi de sakte. Isliye ye provider TOOL CALLS return nahi
    karta — sirf text jawab deta hai. Yahi bade reasoning/coding/
    web-search kaam ke liye chahiye hota hai (jahan device control ki
    zarurat nahi, sirf accha dimaag chahiye).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil

from ..config import ProviderConfig
from .base import LLMProvider
from .types import (
    BrainError,
    LLMResponse,
    Message,
    ModelUnavailableError,
    Role,
    ToolSchema,
)

log = logging.getLogger("saarthi.brain.kiro")

# ANSI escape codes hataane ke liye (colors, cursor moves, etc.)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

# Kiro CLI ki wo lines jo jawab NAHI hain — inhe output se hata dete hain.
_NOISE_MARKERS = (
    "credits:",
    "time:",
    "all tools are now trusted",
    "agents can sometimes do unexpected",
    "learn more at",
    "failed to retrieve mcp",
    "try running `kiro-cli",
    "warning:",
    "mcp functionality disabled",
)

# Kiro ke available models (rate_multiplier = credits ka kharch).
# `--list-models` se aaye. "auto" = task ke hisaab se best chunta hai.
KIRO_MODELS: list[str] = [
    "auto",
    "claude-opus-5", "claude-sonnet-5", "claude-opus-4.8",
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
    "claude-opus-4.7", "claude-opus-4.6", "claude-sonnet-4.6",
    "claude-opus-4.5", "claude-sonnet-4.5", "claude-sonnet-4",
    "claude-haiku-4.5", "deepseek-3.2", "minimax-m2.5", "minimax-m2.1",
    "glm-5", "qwen3-coder-next",
]


class KiroProvider(LLMProvider):
    """Kiro CLI ko subprocess ke roop mein chalane wala provider."""

    # Bade model dheeme hote hain — headless run 2-3 min tak le sakta hai
    DEFAULT_TIMEOUT = 240

    def __init__(self, config: ProviderConfig, binary: str | None = None):
        super().__init__(config)
        # kiro-cli PATH mein hona chahiye. Na mile to chat() pe saaf
        # error milega (mark_dead ke saath).
        self._binary = binary or os.getenv("KIRO_CLI_PATH") or "kiro-cli"

    # ------------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------------

    def _resolve_binary(self) -> str:
        found = shutil.which(self._binary)
        if not found:
            raise ModelUnavailableError(
                "kiro-cli nahi mila. Kiro CLI install kar aur PATH mein "
                "daal, ya .env mein KIRO_CLI_PATH set kar."
            )
        return found

    def _flatten_messages(self, messages: list[Message]) -> str:
        """
        Poori conversation ko ek single prompt string mein badlo.

        Kiro CLI ek hi prompt string leta hai (messages array nahi).
        Isliye system + history + latest user sab ko readable text mein
        jod dete hain. Tool result messages bhi context ke roop mein
        jaate hain.
        """
        parts: list[str] = []
        for msg in messages:
            content = (msg.content or "").strip()
            if not content and not msg.tool_calls:
                continue

            if msg.role == Role.SYSTEM:
                parts.append(f"[System instructions]\n{content}")
            elif msg.role == Role.USER:
                # Image messages: text hi bhejte hain (Kiro CLI ko base64
                # image pass karne ka seedha tareeka nahi hai headless mein)
                parts.append(f"[User]\n{content}" if content else "")
            elif msg.role == Role.ASSISTANT:
                if content:
                    parts.append(f"[Assistant]\n{content}")
            elif msg.role == Role.TOOL:
                parts.append(f"[Tool result]\n{content}")

        return "\n\n".join(p for p in parts if p).strip()

    def _clean_output(self, raw: str) -> str:
        """
        kiro-cli ke raw stdout se saaf jawab nikaalo.

        Hataata hai: ANSI codes, `> ` prompt markers, aur credits/
        warning/trust jaisi noise lines.
        """
        text = _ANSI.sub("", raw or "")

        clean_lines: list[str] = []
        for line in text.splitlines():
            # ANSI ke baad trailing space hatao, PAR leading indentation
            # RAKHO — code blocks ke liye zaroori hai (warna Python code
            # ka indentation tut jaata hai).
            line = line.rstrip()
            stripped = line.strip()

            if not stripped:
                clean_lines.append("")
                continue

            lowered = stripped.lower()
            if any(marker in lowered for marker in _NOISE_MARKERS):
                continue

            # Kiro reply ke aage "> " ya "▸" marker lagata hai — sirf wahi
            # hata do (leading code-indentation ko haath mat lagao).
            line = re.sub(r"^(\s*)[>▸•]\s+", r"\1", line)
            clean_lines.append(line)

        result = "\n".join(clean_lines).strip()
        # Ek se zyada khaali line ko ek mein badlo
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result

    # ------------------------------------------------------------------
    #  Model discovery
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """Kiro ke available models (static list — CLI se verify kiya)."""
        return list(KIRO_MODELS)

    # ------------------------------------------------------------------
    #  Main call
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Kiro CLI ko headless chalao aur clean text jawab do.

        `tools` yahan IGNORE hota hai — Kiro apne tools use karta hai,
        SAARTHI ke nahi. Ye provider sirf text reasoning/coding/search
        ke liye hai (dekh module docstring).
        """
        binary = self._resolve_binary()
        prompt = self._flatten_messages(messages)
        if not prompt:
            raise BrainError("kiro: khali prompt — bhejne ko kuch nahi")

        args = [
            binary,
            "chat",
            "--no-interactive",
            "--trust-tools=",   # koi tool nahi — sirf jawab, safe default
            "--wrap", "never",
        ]
        # Model select karo (default "auto" = task ke hisaab se best)
        model = (self.model or "auto").strip()
        if model:
            args += ["--model", model]
        args.append(prompt)

        # KIRO_API_KEY env mein bhejo — CLI isi se authenticate karti hai
        env = dict(os.environ)
        if self.config.api_key:
            env["KIRO_API_KEY"] = self.config.api_key

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ModelUnavailableError(f"kiro-cli chal nahi paya: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise BrainError(f"kiro: subprocess start fail — {exc}") from exc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.DEFAULT_TIMEOUT
            )
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise BrainError(
                f"kiro: {self.DEFAULT_TIMEOUT}s mein jawab nahi aaya "
                f"(bada task tha? chhote hisson mein bol)"
            ) from exc

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        reply = self._clean_output(stdout)

        # kiro-cli ANSI/warnings ki wajah se exit code 1 de sakti hai
        # CHAHE jawab mil gaya ho. Isliye pehle reply check karo.
        if not reply:
            lowered = (stderr + stdout).lower()
            if "unauthor" in lowered or "invalid api key" in lowered or "401" in lowered:
                raise ModelUnavailableError(
                    "kiro: API key galat ya expire — .env mein KIRO_API_KEY check kar"
                )
            if "not logged in" in lowered or "login" in lowered:
                raise ModelUnavailableError(
                    "kiro: authenticate nahi hua — `kiro-cli login` chala ya "
                    "KIRO_API_KEY set kar"
                )
            raise BrainError(
                f"kiro: khali jawab aaya (exit {proc.returncode}). "
                f"stderr: {self._clean_output(stderr)[:200]}"
            )

        # Token usage Kiro CLI se reliably nahi milta — 0 rakhte hain
        return LLMResponse(
            text=reply,
            tool_calls=[],
            provider=self.name,
            model=model,
        )
