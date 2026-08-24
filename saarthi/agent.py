"""
SAARTHI Agent — sab kuch yahan judta hai.

Loop simple hai (jaan-boojh ke):

    1. User ka Hinglish command parse karo -> structured hints
    2. LLM ko bhejo: system prompt + memory + skills + tools
    3. LLM tool chalane bole -> chalao, result wapas do
    4. Repeat, jab tak LLM final jawab na de (ya max_steps khatam)
    5. Sab kuch memory mein log karo

Kyun koi framework (LangGraph/CrewAI) use nahi kiya:
    Kyunki ye loop 100 line ka hai aur samajh mein aata hai. Framework
    laga dete to andar kya ho raha hai kabhi samajh nahi aata. Jab ye
    loop chhota pad jaayega, tab framework laayenge — pehle nahi.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .brain import Brain
from .brain.types import LLMResponse, Message, NoProviderError, Role, ToolCall
from .config import Settings, settings as default_settings
from .devices import DeviceManager
from .lang import build_system_prompt, build_user_message, detect_language, parse
from .memory import MemoryStore
from .skills import SkillRecorder, SkillRunner, SkillStore
from .tools import ToolContext, ToolRegistry, default_registry

log = logging.getLogger("saarthi.agent")


# CLI ye callbacks deta hai — isse agent UI se independent rehta hai
ConfirmCallback = Callable[[str, dict], Awaitable[bool]]
OutputCallback = Callable[[str, str], None]  # (kind, text)


@dataclass
class TurnResult:
    """Ek user command ka result."""

    reply: str
    steps_used: int = 0
    tool_calls: list[str] = field(default_factory=list)
    error: str = ""

    # Agent ne user se sawaal pucha hai?
    question: str | None = None

    @property
    def ok(self) -> bool:
        return not self.error


class Agent:
    """SAARTHI ka main agent."""

    def __init__(
        self,
        config: Settings | None = None,
        brain: Brain | None = None,
        devices: DeviceManager | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryStore | None = None,
        skills: SkillStore | None = None,
        confirm: ConfirmCallback | None = None,
        on_output: OutputCallback | None = None,
    ):
        self.settings = config or default_settings

        # --- Core parts ---
        self.brain = brain or Brain(self.settings)
        self.devices = devices or DeviceManager(self.settings)
        if not self.devices.devices:
            self.devices.setup_defaults()

        self.tools = tools or default_registry()
        self.memory = memory or MemoryStore()
        self.skills = skills or SkillStore()

        # --- Dikha Do Mode ---
        self.recorder = SkillRecorder()
        self.runner = SkillRunner(
            registry=self.tools, store=self.skills, brain=self.brain
        )

        # --- Callbacks ---
        self.confirm = confirm
        self.on_output = on_output or (lambda kind, text: None)

        # Brain ko UI se jod do.
        #
        # Kyun: provider fail hone pe Brain `log.warning` karta tha, aur
        # Python ka lastResort handler use SEEDHA stderr pe chhap deta
        # tha — bilkul beech mein, bina rang, look todte hue. Ab wo
        # khabar normal activity line ban ke aati hai.
        self.brain.notify = lambda kind, text: self.on_output(kind, text)

        # --- Conversation state ---
        self.session_id = uuid.uuid4().hex[:12]
        self.messages: list[Message] = []
        self._system_prompt: str | None = None

    # ------------------------------------------------------------------
    #  Setup
    # ------------------------------------------------------------------

    def _build_context(self) -> ToolContext:
        """Tools ko dene wala context."""
        return ToolContext(
            devices=self.devices,
            settings=self.settings,
            confirm=self.confirm,
            memory=self.memory,
            skills=self.skills,
            scratch={
                "recorder": self.recorder,
                "skill_runner": self.runner,
            },
        )

    async def refresh_system_prompt(self) -> str:
        """
        System prompt banao — devices, memory aur skills ke saath.

        Har turn pe dobara nahi banate (tokens bachte hain), sirf
        session start pe ya jab kuch badle.
        """
        device_info = await self.devices.describe()
        memory_context = await self.memory.build_context()
        known_skills = await self.skills.build_context()

        self._system_prompt = build_system_prompt(
            language=self.settings.language,
            device_info=device_info,
            memory_context=memory_context or None,
            known_skills=known_skills or None,
        )
        return self._system_prompt

    async def start_session(self) -> None:
        """Naya session shuru karo."""
        prompt = await self.refresh_system_prompt()
        self.messages = [Message.system(prompt)]
        log.info("Session shuru: %s", self.session_id)

    # ------------------------------------------------------------------
    #  Main turn
    # ------------------------------------------------------------------

    async def run_turn(self, user_input: str) -> TurnResult:
        """
        Ek user command process karo.

        Ye main entry point hai — CLI, voice, ya server sab isi ko
        call karte hain.
        """
        if not self.messages:
            await self.start_session()

        if not self.brain.is_ready:
            return TurnResult(
                reply="",
                error=self.settings.setup_help(),
            )

        # --- PILLAR #1: Hinglish parse karo ---
        parsed = parse(user_input)

        # User ne kis bhasha mein likha? Usi mein jawab dena hai.
        #
        # Ye HAR TURN pe detect hota hai (session ke shuru mein ek baar
        # nahi) kyunki user beech mein bhasha badal sakta hai — ek
        # message English, agla Hinglish. Interface English hai, par
        # BAAT user ki bhasha mein hoti hai.
        #
        # settings.language mein "hinglish"/"english" fix kiya ho to
        # wahi use hota hai — auto-detect override nahi karta.
        configured = (self.settings.language or "auto").lower()
        if configured == "auto":
            reply_language = detect_language(user_input)
        else:
            reply_language = configured

        if self.settings.debug:
            hint = parsed.to_hint()
            if hint:
                self.on_output("debug", hint)
            self.on_output("debug", f"bhasha: {reply_language}")

        # Structured hints ke saath LLM ko bhejo
        self.messages.append(
            Message.user(build_user_message(parsed, reply_language))
        )

        # Memory mein log karo
        await self.memory.log_turn(self.session_id, "user", user_input)

        ctx = self._build_context()
        tool_schemas = self.tools.schemas(available_only_for=ctx)

        used_tools: list[str] = []
        steps = 0

        # --- Plan-Act-Observe loop ---
        while steps < self.settings.max_steps:
            steps += 1

            try:
                response: LLMResponse = await self.brain.think(
                    messages=self.messages,
                    tools=tool_schemas,
                )
            except NoProviderError as exc:
                return TurnResult(reply="", error=str(exc), steps_used=steps)
            except Exception as exc:  # noqa: BLE001
                log.exception("Brain fail hua")
                return TurnResult(
                    reply="",
                    error=f"LLM se jawab nahi mila: {exc}",
                    steps_used=steps,
                )

            # --- LLM ne final jawab diya ---
            if not response.wants_tools:
                reply = response.text or "(kuch jawab nahi aaya)"
                self.messages.append(Message.assistant(reply))
                await self.memory.log_turn(self.session_id, "assistant", reply)

                return TurnResult(
                    reply=reply,
                    steps_used=steps,
                    tool_calls=used_tools,
                )

            # --- LLM tools chalana chahta hai ---
            self.messages.append(
                Message.assistant(response.text, tool_calls=response.tool_calls)
            )

            if response.text:
                self.on_output("thinking", response.text)

            pending_question: str | None = None

            for call in response.tool_calls:
                used_tools.append(call.name)
                self.on_output("tool", str(call))

                result = await self.tools.execute(call, ctx)

                # --- DIKHA DO MODE: step record karo ---
                self._record_if_learning(call, result)

                # Tool ka result LLM ko wapas do
                content = result.output if result.ok else f"FAIL: {result.error}"

                # Screenshot mila? To image ke saath bhejo (Gemini dekhega)
                image_b64 = result.data.get("image_b64")
                if image_b64:
                    self.messages.append(
                        Message.tool_result(
                            content or "screenshot liya", call.id
                        )
                    )
                    self.messages.append(
                        Message.user(
                            "Ye screen ka screenshot hai — dekh ke bata "
                            "aage kya karna hai.",
                            image_b64=image_b64,
                        )
                    )
                else:
                    self.messages.append(
                        Message.tool_result(content, call.id)
                    )

                self.on_output(
                    "result" if result.ok else "error",
                    content[:500],
                )

                # Agent ne user se sawaal pucha
                if result.data.get("needs_user_input"):
                    pending_question = result.data.get("question")

            # Sawaal pucha hai to user ka jawab chahiye — loop rok do
            if pending_question:
                self.messages.append(Message.assistant(pending_question))
                await self.memory.log_turn(
                    self.session_id, "assistant", pending_question
                )
                return TurnResult(
                    reply=pending_question,
                    steps_used=steps,
                    tool_calls=used_tools,
                    question=pending_question,
                )

        # --- Steps khatam ho gaye ---
        message = (
            f"{self.settings.max_steps} steps ho gaye par kaam pura nahi hua. "
            f"Thoda simple bata de ya chhote hisson mein bol."
        )
        self.messages.append(Message.assistant(message))
        return TurnResult(
            reply=message,
            steps_used=steps,
            tool_calls=used_tools,
            error="max steps limit",
        )

    # ------------------------------------------------------------------
    #  Dikha Do Mode
    # ------------------------------------------------------------------

    def _record_if_learning(self, call: ToolCall, result) -> None:
        """
        Recording ON hai to ye step yaad rakh lo.

        Recorder khud decide karta hai kya record karna hai —
        read-only aur failed steps skip ho jaate hain.
        """
        if not self.recorder.recording:
            return

        # Element ke coordinates mile? Self-healing fallback ke liye rakho
        coords = None
        output = result.output or ""
        if result.ok and "tap kiya (" in output:
            try:
                inside = output.split("(")[-1].split(")")[0]
                x_str, y_str = inside.split(",")
                coords = (int(x_str.strip()), int(y_str.strip()))
            except (ValueError, IndexError):
                coords = None

        self.recorder.capture(
            action=call.name,
            params=dict(call.arguments),
            succeeded=result.ok,
            target_coords=coords,
        )

    # ------------------------------------------------------------------
    #  Utilities
    # ------------------------------------------------------------------

    def reset_conversation(self) -> None:
        """Baat bhool jao (memory nahi, sirf current chat)."""
        system = self.messages[0] if self.messages else None
        self.messages = [system] if system else []
        self.session_id = uuid.uuid4().hex[:12]

    def trim_history(self, keep_messages: int = 40) -> int:
        """
        Purane messages hatao — free tier ke tokens bachane ke liye.

        System prompt hamesha rakhte hain.
        """
        if len(self.messages) <= keep_messages + 1:
            return 0

        system = self.messages[0]
        recent = self.messages[-keep_messages:]
        removed = len(self.messages) - len(recent) - 1
        self.messages = [system] + recent
        return removed

    async def status(self) -> str:
        """Agent ka pura status — CLI ke liye."""
        lines: list[str] = []

        lines.append("BRAIN (LLM providers):")
        lines.append(self.brain.status())

        lines.append("")
        lines.append("DEVICES:")
        lines.append(await self.devices.describe())

        lines.append("")
        lines.append(f"TOOLS: {len(self.tools)} available")

        mem_stats = await self.memory.stats()
        lines.append("")
        lines.append(
            f"MEMORY: {mem_stats['facts']} facts, "
            f"{mem_stats['messages']} messages"
        )

        skill_stats = await self.skills.stats()
        lines.append(
            f"SKILLS: {skill_stats['skills']} seekhi hui "
            f"({skill_stats['steps']} steps, "
            f"{skill_stats['total_runs']} baar chali)"
        )

        if self.recorder.recording:
            lines.append("")
            lines.append(
                f"DIKHA DO MODE: ON ({self.recorder.step_count} steps record hue)"
            )

        lines.append("")
        lines.append(f"Language: {self.settings.language}")
        lines.append(
            f"Risky confirmation: "
            f"{'ON' if self.settings.confirm_risky else 'OFF (khatarnak!)'}"
        )

        return "\n".join(lines)
