"""
SAARTHI Agent — sab kuch yahan judta hai.

Loop simple hai (jaan-boojh ke):

    1. User ka Hinglish command parse karo -> structured hints
    2. LLM ko bhejo: system prompt + memory + skills + tools
    3. LLM tool chalane bole -> chalao, result wapas do
    4. Repeat, jab tak LLM final jawab na de (ya max_steps khatam)
    5. Sab kuch memory mein log karo

v2 ENHANCEMENTS:
    - STREAMING: LLM ka jawab token-by-token aata hai, user ko turant dikhta
    - PARALLEL TOOLS: Multiple tool calls ek saath chalte hain (asyncio.gather)
    - Faster response time due to real-time output

Kyun koi framework (LangGraph/CrewAI) use nahi kiya:
    Kyunki ye loop 100 line ka hai aur samajh mein aata hai. Framework
    laga dete to andar kya ho raha hai kabhi samajh nahi aata. Jab ye
    loop chhota pad jaayega, tab framework laayenge — pehle nahi.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .brain import Brain
from .brain.types import LLMResponse, Message, NoProviderError, Role, StreamChunk, ToolCall
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

# Tools jo PARALLEL mein safe nahi hain (order dependent)
# In tools ka output agla tool use karta hai, isliye sequential chahiye
_SEQUENTIAL_TOOLS = frozenset({
    "tap_karo", "text_pe_tap", "field_bharo", "key_dabao",
    "scroll_karo", "swipe_karo", "back_jao",
    "screenshot_lo", "screen_padho",
})


# ----------------------------------------------------------------------
#  BIG TASK detection — Kiro escalation ke liye
# ----------------------------------------------------------------------
#
# Kiro (kiro-cli) ke andar bade models hain (Claude Opus 5, GPT-5.6,
# Qwen coder). Wo coding / web-search / complex reasoning ke liye best
# hai — PAR slow aur credit-mehenga. Isliye har chhoti baat pe nahi,
# sirf BADE kaam pe use karte hain.
#
# Ye detection device-control kaam ko CHHOD deta hai (app kholo, tap
# karo, gaana chala) — wo SAARTHI ke apne tools se hota hai, Kiro se
# nahi. Kiro ko sirf "dimaag" wala kaam milta hai.

# Coding / technical
_BIG_CODING = (
    "code", "coding", "program", "programming", "script", "function",
    "debug", "bug fix", "error fix", "refactor", "algorithm", "leetcode",
    "python", "javascript", "java ", "c++", "html", "css", "sql", "react",
    "api ", "regex", "compile", "stack trace", "exception",
    "likh de code", "code likh", "program bana", "script bana",
)
# Web search / research
_BIG_SEARCH = (
    "search the web", "web search", "research", "latest news", "find online",
    "look up", "internet pe search", "web pe dhoondh", "online dhoondh",
    "compare ", "explain in detail", "detail mein samjha", "vistaar se",
)
# Complex / long
_BIG_COMPLEX = (
    "write an essay", "essay likh", "write a blog", "blog likh",
    "detailed plan", "step by step guide", "analyze", "analysis",
    "summarize this", "poora samjha", "in depth",
)
# Document banana — PDF/Excel/PPT/Word (dedicated tools se, par ye
# BADA/structured kaam hai, chhota model aksar galat structure deta hai)
_BIG_DOCUMENT = (
    "pdf bana", "pdf banao", "pdf file", "make a pdf", "create pdf",
    "excel bana", "excel banao", "spreadsheet", "marksheet", "excel sheet",
    "ppt bana", "ppt banao", "presentation", "slides bana", "powerpoint",
    "word document", "word file", "resume bana", "report bana",
    "document bana", "notes bana", "notes banao",
)

_BIG_TASK_MARKERS = _BIG_CODING + _BIG_SEARCH + _BIG_COMPLEX + _BIG_DOCUMENT


# ----------------------------------------------------------------------
#  AUTO MODEL ROUTING — task ki size ke hisaab se model chuno
# ----------------------------------------------------------------------
#
# User ki complaint thi: "bar-bar bluesminds use hota hai". Wo chahta
# hai ki chhota kaam chhote/tez model ko jaaye aur bada kaam bade/smart
# model ko. Ye function decide karta hai kaun-se providers PEHLE try
# karne hain (prefer list).
#
# Ye order ko REPLACE nahi karta — sirf preference set karta hai. Jo
# provider available/healthy nahi hoga wo apne aap skip ho jaayega
# (router.py handle karta hai), to fallback safe rehta hai.

# Chhote/tez providers — ek line ka jawab, device control, quick sawaal
_FAST_PROVIDERS = ["gemini", "groq", "kiraai", "kiraai_kira", "bluesminds"]

# Bade/smart providers — coding, research, structured documents, essays
_SMART_PROVIDERS = ["deepseek", "nvidia", "opencode", "muse", "bluesminds"]

# Device-control ke shabd — ye HAMESHA chhota kaam hai (fast model),
# chahe prompt lamba ho. App kholo/tap/gaana chalao waghairah.
_DEVICE_MARKERS = (
    "kholo", "khol de", "open ", "chala do", "chalao", "play ",
    "tap", "click", "scroll", "swipe", "screenshot", "notification",
    "volume", "call ", "message bhej", "whatsapp", "youtube",
)


def _classify_task_size(text: str) -> str:
    """
    Task chhota hai, bada hai, ya beech ka?

    Returns: "chhota" | "bada" | "medium"

    - chhota: device control, ek line ka sawaal (fast model)
    - bada:   coding / research / document / essay / bahut lamba prompt
    - medium: baaki sab (default order chalega)
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return "medium"

    words = lowered.split()

    # Device control = chhota (chahe keyword bada lage)
    if any(marker in lowered for marker in _DEVICE_MARKERS):
        # ...par agar saath mein coding/document ka kaam bhi hai to bada
        if any(m in lowered for m in (_BIG_CODING + _BIG_DOCUMENT)):
            return "bada"
        return "chhota"

    # Clearly bada kaam
    if any(marker in lowered for marker in _BIG_TASK_MARKERS):
        return "bada"

    # Bahut lamba prompt = bada
    if len(words) >= 40:
        return "bada"

    # Bahut chhota prompt = chhota (ek-do line ka sawaal/command)
    if len(words) <= 8:
        return "chhota"

    return "medium"


def _preferred_providers_for(text: str) -> list[str] | None:
    """
    Is task ke liye kaun-se providers pehle try karein?

    None = koi khaas preference nahi (default order chalega).
    """
    size = _classify_task_size(text)
    if size == "chhota":
        return _FAST_PROVIDERS
    if size == "bada":
        return _SMART_PROVIDERS
    return None


def _looks_like_big_task(text: str) -> bool:
    """
    User ka command BADA kaam hai? (coding / web-search / complex)

    Sirf tabhi True jab clearly technical/research/complex ho. Rozmarra
    ki baat ("mausam", "gaana chala", "app kholo") pe False — wo fast
    providers + device tools se hoti hai.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return False

    # Short device commands are NOT big tasks even if a keyword slips in
    if any(marker in lowered for marker in _BIG_TASK_MARKERS):
        return True

    # Bahut lamba/tafseeli sawaal (device command nahi) — bada maano
    if len(lowered.split()) >= 40:
        return True

    return False


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

        # --- Screenshot caching ---
        # Tokens bachane ke liye: sirf latest N screenshots rakho,
        # aur same screenshot dobara bhejne se baho (dedupe).
        self._last_screenshot_hash: str | None = None
        self._screenshot_msg_indices: list[int] = []  # positions of image messages

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
    #  Main turn — STREAMING + PARALLEL TOOLS
    # ------------------------------------------------------------------

    async def run_turn(self, user_input: str, image_b64: str | None = None) -> TurnResult:
        """
        Ek user command process karo — STREAMING ke saath.

        Ye main entry point hai — CLI, voice, ya server sab isi ko
        call karte hain.

        v2: Ab response STREAM hota hai — user ko turant tokens dikhne
        lagte hain. Aur multiple tool calls PARALLEL mein chalte hain
        (jab tak wo independent hain).

        image_b64: User ne koi image/screenshot attach ki ho (base64,
        bina data-uri prefix). Iske saath user ka message vision-capable
        provider (Gemini/Muse) ko jaata hai — router khud aisa provider
        chun leta hai kyunki message mein image hoti hai.
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
        configured = (self.settings.language or "auto").lower()
        if configured == "auto":
            reply_language = detect_language(user_input)
        else:
            reply_language = configured

        if self.settings.debug:
            hint = parsed.to_hint()
            if hint:
                self.on_output("debug", hint)
            self.on_output("debug", f"language: {reply_language}")

        # Structured hints ke saath LLM ko bhejo.
        # Image attach hui ho to usi user message ke saath bhejo —
        # router.py dekh lega ki image hai aur vision provider chunega.
        self.messages.append(
            Message.user(
                build_user_message(parsed, reply_language),
                image_b64=image_b64,
            )
        )

        # --- VISION GUARD ---
        # User ne image bheji, par koi vision-capable provider (jiske
        # paas key ho aur jo chalu ho) available nahi? To chup mat raho —
        # warna text-only model image ko IGNORE kar deta hai aur user ko
        # lagta hai "kuch hua hi nahi". Saaf batao ki kya karna hai.
        if image_b64 is not None and not self.brain.has_vision:
            msg = (
                "I received the image, but no model that can SEE images "
                "is active right now.\n"
                "To understand screenshots you need Gemini (or Muse/Gemma).\n"
                "Easiest: add GEMINI_API_KEY in .env "
                "(free: https://aistudio.google.com/apikey), then restart."
            )
            self.on_output("error", msg)
            if self.messages and self.messages[-1].has_image:
                self.messages.pop()
            return TurnResult(reply="", error=msg)

        # Memory mein log karo
        await self.memory.log_turn(self.session_id, "user", user_input)

        # --- KIRO ESCALATION: bade kaam bade model se ---
        #
        # Coding / web-search / complex reasoning ho aur Kiro available
        # ho, to us turn ke liye Kiro (bade model) se seedha jawab lo.
        # Ye device-control nahi karta (tools nahi) — sirf dimaag wala
        # kaam. Fail ho to normal loop pe gir jaate hain.
        #
        # Image attach ho to Kiro skip — wo vision nahi karta, image
        # wala kaam Gemini/Muse ko jaana chahiye.
        if image_b64 is None and self._should_use_kiro(user_input):
            kiro_result = await self._answer_with_kiro()
            if kiro_result is not None:
                return kiro_result
            # Kiro fail — normal providers se karo (graceful fallback)
            self.on_output("debug", "kiro did not work — trying normal providers")

        ctx = self._build_context()
        tool_schemas = self.tools.schemas(available_only_for=ctx)

        # --- AUTO MODEL ROUTING ---
        # Task ki size dekh ke decide karo kaun-se providers pehle try
        # karne hain. Chhota kaam -> fast model, bada kaam -> smart model.
        # None = default order. Ye har step pe same rehta hai is turn ke.
        prefer = _preferred_providers_for(user_input)
        if self.settings.debug and prefer:
            self.on_output(
                "debug",
                f"task size: {_classify_task_size(user_input)} -> "
                f"prefer {', '.join(prefer[:3])}...",
            )

        used_tools: list[str] = []
        steps = 0

        # --- Plan-Act-Observe loop (STREAMING) ---
        while steps < self.settings.max_steps:
            steps += 1

            try:
                # STREAMING: token-by-token output
                streamed_text = ""
                final_tool_calls: list[ToolCall] = []

                async for chunk in self.brain.think_stream(
                    messages=self.messages,
                    tools=tool_schemas,
                    prefer=prefer,
                ):
                    # Real-time text output — user ko turant dikhao
                    if chunk.delta:
                        streamed_text += chunk.delta
                        self.on_output("stream", chunk.delta)

                    # Final chunk — tool calls aur usage info
                    if chunk.is_final:
                        final_tool_calls = chunk.tool_calls

                # Build response from stream
                response = LLMResponse(
                    text=streamed_text,
                    tool_calls=final_tool_calls,
                    prompt_tokens=chunk.prompt_tokens if chunk else 0,
                    completion_tokens=chunk.completion_tokens if chunk else 0,
                )

            except NoProviderError as exc:
                return TurnResult(reply="", error=str(exc), steps_used=steps)
            except Exception as exc:  # noqa: BLE001
                log.exception("Brain fail hua")
                return TurnResult(
                    reply="",
                    error=f"No reply from the LLM: {exc}",
                    steps_used=steps,
                )

            # --- LLM ne final jawab diya (no tools) ---
            if not response.wants_tools:
                reply = response.text or "(no reply came back)"
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

            # --- PARALLEL TOOL EXECUTION ---
            pending_question: str | None = None
            tool_results = await self._execute_tools_parallel(
                response.tool_calls, ctx, used_tools
            )

            # Process results
            for call, result in tool_results:
                # --- DIKHA DO MODE: step record karo ---
                self._record_if_learning(call, result)

                content = result.output if result.ok else f"FAIL: {result.error}"

                # Screenshot mila? To image ke saath bhejo (WITH CACHING)
                image_b64 = result.data.get("image_b64")
                if image_b64:
                    # Tool result HAMESHA append karo (API contract)
                    self.messages.append(
                        Message.tool_result(
                            content or "screenshot liya", call.id
                        )
                    )

                    # DEDUPE: same screenshot dobara mat bhejo.
                    #
                    # ⚠️ POORA string hash karo, pehle 1000 byte NAHI.
                    #
                    # Pehle `image_b64.encode()[:1000]` tha. Wo GALAT tha:
                    # do alag screenshot ka PNG header + shuruaati data
                    # same ho sakta hai (same app, same size, badlav neeche
                    # ki taraf). Tab hum jhooth bol dete — "screen mein koi
                    # badlav nahi hua" — jabki screen badal gayi thi. Agent
                    # phir wahi kaam dohraata ya haar maan leta.
                    #
                    # 1-2 MB pe sha256 kuch millisecond leta hai. LLM call
                    # ke saamne wo kuch bhi nahi.
                    img_hash = hashlib.sha256(image_b64.encode()).hexdigest()
                    dedupe = getattr(self.settings, "screenshot_dedupe", True)
                    max_shots = getattr(self.settings, "max_screenshots", 2)

                    if max_shots <= 0:
                        # Vision band hai — image bhejna hi nahi hai.
                        #
                        # Pehle yahan bug tha: `_evict_old_screenshots()`
                        # purane hata deta tha par NAYA image phir bhi
                        # append ho jaata tha. Matlab
                        # SAARTHI_MAX_SCREENSHOTS=0 pe bhi ek image jaati
                        # thi — setting ka matlab hi khatam.
                        self._evict_old_screenshots()
                        self.messages.append(
                            Message.user(
                                "Screenshot liya gaya par vision band hai "
                                "(SAARTHI_MAX_SCREENSHOTS=0). "
                                "screen_padho use kar."
                            )
                        )
                    elif dedupe and img_hash == self._last_screenshot_hash:
                        # Same screen — image bhejne ki zarurat nahi
                        self.messages.append(
                            Message.user(
                                "Screenshot same hai — screen mein koi "
                                "badlav nahi hua."
                            )
                        )
                    else:
                        # Naya screenshot — EVICT purane, append naya
                        self._evict_old_screenshots()
                        self.messages.append(
                            Message.user(
                                "Ye screen ka screenshot hai — dekh ke bata "
                                "aage kya karna hai.",
                                image_b64=image_b64,
                            )
                        )
                        # Track this image message index
                        self._screenshot_msg_indices.append(len(self.messages) - 1)
                        self._last_screenshot_hash = img_hash
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
            f"Reached {self.settings.max_steps} steps but the task is not "
            f"complete. Try describing it more simply, or in smaller parts."
        )
        self.messages.append(Message.assistant(message))
        return TurnResult(
            reply=message,
            steps_used=steps,
            tool_calls=used_tools,
            error="max steps limit",
        )

    # ------------------------------------------------------------------
    #  Kiro escalation — bade kaam bade model se
    # ------------------------------------------------------------------

    def _should_use_kiro(self, user_input: str) -> bool:
        """
        Is turn ke liye Kiro (bada model) use karein?

        Haan tab jab: (1) Kiro available hai, aur (2) ye BADA kaam hai
        (coding / web-search / complex). Chhoti baat aur device-control
        normal fast providers + tools se hoti hai.
        """
        has_kiro = any(
            p.name == "kiro" for p in self.brain.providers
            if self.brain._is_usable(p)
        )
        if not has_kiro:
            return False
        return _looks_like_big_task(user_input)

    async def _answer_with_kiro(self) -> TurnResult | None:
        """
        Kiro se seedha text jawab lo (bina SAARTHI tools ke).

        Coding / web-search / complex reasoning ke liye. Kiro apne andar
        ke bade model + apne tools use karta hai. Yahan hum use SAARTHI
        ke tools NAHI dete — sirf ek accha text jawab chahiye.

        Returns:
            TurnResult jab jawab mil gaya, warna None (caller normal
            providers pe gir jaaye).
        """
        # Kaunsa Kiro model chalega ye .env (KIRO_MODEL) se aata hai
        kiro_model = "auto"
        for p in self.brain.providers:
            if p.name == "kiro":
                kiro_model = p.model or "auto"
                break

        # Note: pehle yahan ek visible "Bada kaam detect hua -> Kiro..."
        # line dikhti thi. User ko wo shor lagta tha, isliye ab kuch
        # nahi dikhate — spinner label khud model ka naam dikha deta hai.
        _ = kiro_model  # (rakha hua hai taaki aage zarurat pe use ho sake)

        try:
            # tools=None taaki Kiro pure text reasoning kare.
            # prefer=["kiro"] taaki wo sabse pehle try ho.
            response = await self.brain.think(
                messages=self.messages,
                tools=None,
                prefer=["kiro"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Kiro escalation fail: %s", exc)
            return None

        # Kiro se hi jawab aaya na? (fallback se koi aur provider bhi
        # aa sakta hai — wo bhi theek hai, jawab to mila)
        reply = (response.text or "").strip()
        if not reply:
            return None

        self.on_output("stream", reply)
        self.messages.append(Message.assistant(reply))
        await self.memory.log_turn(self.session_id, "assistant", reply)

        provider_used = response.provider or "kiro"
        # tool_calls tag mein model bhi — CLI verbose mode mein dikhega
        # (e.g. "kiro:auto"), taaki pata chale kaunsa model chala.
        tag = f"kiro:{response.model}" if provider_used == "kiro" and response.model else provider_used
        return TurnResult(
            reply=reply,
            steps_used=1,
            tool_calls=[f"[{tag}]"],
        )

    # ------------------------------------------------------------------
    #  Parallel Tool Execution
    # ------------------------------------------------------------------

    async def _execute_tools_parallel(
        self,
        tool_calls: list[ToolCall],
        ctx: ToolContext,
        used_tools: list[str],
    ) -> list[tuple[ToolCall, object]]:
        """
        Multiple tool calls ko parallel mein chalao (jab safe ho).

        STRATEGY:
        - Agar saare tools independent hain (search, memory, etc.)
          -> asyncio.gather se ek saath chalao
        - Agar koi bhi tool UI-dependent hai (tap, type, scroll)
          -> sequential chalao (order matters)
        - Mixed case: independent pehle parallel, phir sequential

        Returns: [(ToolCall, ActionResult), ...] in original order
        """
        if len(tool_calls) <= 1:
            # Single tool — no parallelization needed
            results = []
            for call in tool_calls:
                used_tools.append(call.name)
                self.on_output("tool", str(call))
                result = await self.tools.execute(call, ctx)
                results.append((call, result))
            return results

        # Classify tools: independent vs sequential
        has_sequential = any(
            call.name in _SEQUENTIAL_TOOLS for call in tool_calls
        )

        if has_sequential:
            # Any UI-dependent tool means ALL must run in order
            # (because later tools depend on screen state from earlier ones)
            results = []
            for call in tool_calls:
                used_tools.append(call.name)
                self.on_output("tool", str(call))
                result = await self.tools.execute(call, ctx)
                results.append((call, result))
            return results

        # ALL tools are independent — run in PARALLEL!
        self.on_output(
            "debug",
            f"{len(tool_calls)} independent tools — parallel execution",
        )

        async def _run_one(call: ToolCall):
            used_tools.append(call.name)
            self.on_output("tool", str(call))
            result = await self.tools.execute(call, ctx)
            return (call, result)

        # asyncio.gather — sab ek saath chalenge
        tasks = [_run_one(call) for call in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    # ------------------------------------------------------------------
    #  Screenshot Caching — tokens bachao
    # ------------------------------------------------------------------

    def _evict_old_screenshots(self) -> None:
        """
        Purane screenshot messages hatao — sirf latest N rakho.

        IMPORTANT: Sirf Message.user(..., image_b64=...) messages ko
        evict karna hai. Message.tool_result() ko KABHI mat chhedna —
        warna LLM API "tool_call_id without response" error dega.

        Evicted message ki jagah placeholder text daal dete hain taaki
        message index sahi rahe (list se pop karna indices tod deta).
        """
        max_screenshots = getattr(self.settings, "max_screenshots", 2)

        if max_screenshots <= 0:
            # All screenshots disabled — evict everything
            for idx in self._screenshot_msg_indices:
                if idx < len(self.messages):
                    self.messages[idx] = Message.user(
                        "(screenshot removed — vision disabled)"
                    )
            self._screenshot_msg_indices.clear()
            return

        # Keep only latest N, evict older ones
        while len(self._screenshot_msg_indices) >= max_screenshots:
            old_idx = self._screenshot_msg_indices.pop(0)
            if old_idx < len(self.messages):
                self.messages[old_idx] = Message.user(
                    "(old screenshot removed — saving tokens)"
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
        self._last_screenshot_hash = None
        self._screenshot_msg_indices = []

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
