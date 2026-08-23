"""
Skill Runner — seekhi hui skill ko chalana, SELF-HEALING ke saath.

YAHI TERA ASLI INNOVATION HAI.

Problem jo har automation tool mein hai:
    Tasker, MacroDroid, normal macros — sab coordinates pe chalte hain.
    App update aaya, button 50 pixel neeche chala gaya -> AUTOMATION TOOT GAYA.
    User ko dobara pura setup karna padta hai.

SAARTHI ka solution — 3 level ka healing:

    LEVEL 1: target_text se element dhoondo
             (button ka text same rehta hai chahe position badle)

    LEVEL 2: text na mile to coordinates try karo
             (fallback — UI same hai, sirf text badla)

    LEVEL 3: dono fail? LLM ko screen dikhao aur pucho
             "ye kaam karna hai, kahan tap karun?"
             LLM naya raasta dhoondh dega, aur hum skill UPDATE kar denge

Level 3 hi wo cheez hai jo research papers mein hai par kisi phone
agent product mein shipped nahi hai. Isko theek se bana to tera
project genuinely naya hoga.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..devices.base import ActionResult
from .store import Skill, SkillStep

log = logging.getLogger("saarthi.skills.runner")


@dataclass
class StepOutcome:
    """Ek step ka result."""

    step: SkillStep
    ok: bool
    message: str = ""

    # Healing hui? Kaise?
    healed: bool = False
    heal_method: str = ""

    def __str__(self) -> str:
        mark = "OK " if self.ok else "FAIL"
        heal = f" (healed: {self.heal_method})" if self.healed else ""
        return f"[{mark}] {self.step}{heal}"


@dataclass
class SkillRunResult:
    """Poori skill run ka result."""

    skill_name: str
    ok: bool
    outcomes: list[StepOutcome] = field(default_factory=list)
    error: str = ""

    # Kitne steps heal karne pade — ye batata hai skill purani ho rahi hai
    heal_count: int = 0

    @property
    def completed_steps(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    def report(self) -> str:
        """User ko dikhane wala summary."""
        lines: list[str] = []

        if self.ok:
            lines.append(
                f"'{self.skill_name}' ho gaya "
                f"({self.completed_steps}/{len(self.outcomes)} steps)"
            )
        else:
            lines.append(
                f"'{self.skill_name}' pura nahi hua "
                f"({self.completed_steps}/{len(self.outcomes)} steps chale)"
            )
            if self.error:
                lines.append(f"Problem: {self.error}")

        if self.heal_count:
            lines.append(
                f"Dhyan de: {self.heal_count} step khud theek karne pade — "
                f"app ka UI badla lagta hai. Skill update kar di hai."
            )

        for outcome in self.outcomes:
            lines.append(f"  {outcome}")

        return "\n".join(lines)


class SkillRunner:
    """
    Skills chalata hai, aur toote steps khud theek karta hai.

    Use:
        runner = SkillRunner(registry, store)
        result = await runner.run(skill, {"amount": 2500}, ctx)
    """

    def __init__(self, registry, store, brain=None):
        """
        Args:
            registry: ToolRegistry — steps chalane ke liye
            store: SkillStore — stats aur healed skill save karne ke liye
            brain: Brain — Level 3 healing ke liye (optional)
        """
        self.registry = registry
        self.store = store
        self.brain = brain

    # ------------------------------------------------------------------
    #  Main run
    # ------------------------------------------------------------------

    async def run(
        self,
        skill: Skill,
        values: dict[str, object] | None = None,
        ctx=None,
        stop_on_failure: bool = True,
    ) -> SkillRunResult:
        """
        Skill chalao.

        Args:
            skill: Kaunsi skill
            values: Placeholder values, jaise {"amount": 2500}
            ctx: ToolContext
            stop_on_failure: Step fail ho to ruk jaana hai?
        """
        values = values or {}
        result = SkillRunResult(skill_name=skill.name, ok=True)

        # Zaroori values check karo — beech mein fail hone se behtar hai
        needed = skill.required_params()
        missing = needed - set(values)
        if missing:
            result.ok = False
            result.error = (
                f"Ye values chahiye: {', '.join(sorted(missing))}. "
                f"Bata de to chala dunga."
            )
            return result

        skill_changed = False

        for index, step in enumerate(skill.steps, 1):
            outcome = await self._run_step(step, values, ctx)
            result.outcomes.append(outcome)

            if outcome.healed:
                result.heal_count += 1
                skill_changed = True

            if not outcome.ok:
                result.ok = False
                result.error = f"Step {index} pe atak gaya: {outcome.message}"
                if stop_on_failure:
                    break

        # Stats update — isse pata chalta hai skill bharosemand hai ya nahi
        try:
            await self.store.mark_run(skill.name, result.ok)
        except Exception as exc:  # noqa: BLE001 — stats fail ho to kaam na ruke
            log.warning("mark_run fail: %s", exc)

        # Healing hui to updated skill save karo — agli baar seedha chalegi
        if skill_changed and result.ok:
            try:
                await self.store.save(skill, auto_parameterize=False)
                log.info("Healed skill save ho gayi: %s", skill.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("Healed skill save fail: %s", exc)

        return result

    # ------------------------------------------------------------------
    #  Ek step — healing ke saath
    # ------------------------------------------------------------------

    async def _run_step(
        self, step: SkillStep, values: dict[str, object], ctx
    ) -> StepOutcome:
        """Ek step chalao. Fail ho to heal karne ki koshish karo."""
        from ..brain.types import ToolCall

        params = step.resolve(values)

        # --- Normal koshish ---
        call = ToolCall(id=f"skill_{step.action}", name=step.action, arguments=params)
        result = await self.registry.execute(call, ctx)

        if result.ok:
            return StepOutcome(step=step, ok=True, message=result.output)

        # --- Heal karne ki koshish ---
        log.info("Step fail hua, healing try kar raha hun: %s", step)
        return await self._heal_step(step, params, result, ctx)

    async def _heal_step(
        self, step: SkillStep, params: dict, failure: ActionResult, ctx
    ) -> StepOutcome:
        """
        Toota step theek karo.

        ORDER JAAN-BOOJH KE AISA HAI: pehle SEMANTIC healing (LLM),
        phir coordinates.

        Kyun? Ye subtle par bahut important baat hai:

            Agar button ka text nahi mila, matlab UI BADAL GAYA hai.
            Aisi soorat mein purane coordinates pe tap karna KHATARNAK
            hai — wahan ab koi doosra button ho sakta hai. Tap "safal"
            dikhega (ADB ko farak nahi padta), par GALAT kaam ho jaayega.
            Payment screen pe ye bahut bura ho sakta hai.

            Isliye pehle screen padhke samjho ki naya sahi button
            kaunsa hai. Coordinates sirf tab jab screen padh hi na sakein.

        Ye wahi cheez hai jo normal automation (Tasker/macros) galat
        karte hain — wo chup-chaap galat jagah tap kar dete hain.
        """
        from ..brain.types import ToolCall

        # ---- LEVEL 2 (semantic): screen padho, LLM se sahi element pucho ----
        can_read_screen = self._can_read_screen(ctx)

        if self.brain is not None and step.target_text and can_read_screen:
            healed = await self._heal_with_llm(step, ctx)
            if healed:
                return healed

        # ---- LEVEL 3 (coordinates): last resort ----
        # Yahan tab aate hain jab screen padh nahi sakte ya LLM nahi hai.
        if step.action == "text_pe_tap" and step.target_coords:
            x, y = step.target_coords

            if can_read_screen:
                # Screen padh sakte the par sahi element nahi mila —
                # blind tap risky hai. Isliye permission maango.
                approved = await ctx.ask_confirmation(
                    "UI badal gaya lagta hai. Purane coordinates pe tap karun?",
                    {
                        "dhoondh raha tha": step.target_text,
                        "coordinates": f"({x}, {y})",
                        "risk": "wahan ab koi doosra button ho sakta hai",
                    },
                )
                if not approved:
                    return StepOutcome(
                        step=step,
                        ok=False,
                        message=(
                            f"'{step.target_text}' nahi mila aur blind tap "
                            f"karne se mana kar diya. Skill dobara sikha de."
                        ),
                    )

            log.debug("Coordinate healing: (%d,%d)", x, y)
            call = ToolCall(
                id="heal_coords",
                name="coordinate_pe_tap",
                arguments={"x": x, "y": y},
            )
            result = await self.registry.execute(call, ctx)

            if result.ok:
                return StepOutcome(
                    step=step,
                    ok=True,
                    message=result.output,
                    healed=True,
                    heal_method="purane coordinates se (verify kar lena)",
                )

        # ---- Heal nahi hua ----
        return StepOutcome(
            step=step,
            ok=False,
            message=failure.error or "step fail hua",
        )

    def _can_read_screen(self, ctx) -> bool:
        """Screen ka structure padh sakte hain? (UI_TREE capability)"""
        if ctx is None:
            return False
        try:
            from ..devices.base import Capability

            return len(ctx.devices.with_capability(Capability.UI_TREE)) > 0
        except Exception:  # noqa: BLE001
            return False

    async def _heal_with_llm(self, step: SkillStep, ctx) -> StepOutcome | None:
        """
        LEVEL 3 HEALING — asli innovation.

        Screen padho, LLM ko batao kya karna tha, wo naya target dhoondhe.
        Mil jaaye to step ko PERMANENTLY update kar do.
        """
        from ..brain.types import Message, ToolCall

        # Screen ka structure padho
        read_call = ToolCall(id="heal_read", name="screen_padho", arguments={})
        screen = await self.registry.execute(read_call, ctx)

        if not screen.ok:
            return None

        elements = screen.data.get("interactive") or screen.data.get("elements") or []
        if not elements:
            return None

        # LLM ko options do
        options = "\n".join(f"  - {el.label}" for el in elements[:30] if el.label)

        prompt = (
            f"Ek automation step toot gaya hai.\n\n"
            f'Pehle "{step.target_text}" pe tap karna tha, par wo ab '
            f"screen pe nahi mil raha (app ka UI badal gaya lagta hai).\n\n"
            f"Screen pe ab ye options hain:\n{options}\n\n"
            f'Inme se kaunsa option "{step.target_text}" ka kaam karega?\n'
            f"Sirf us option ka exact text likh, aur kuch nahi. "
            f"Koi bhi sahi na lage to likh: NAHI_MILA"
        )

        try:
            answer = (await self.brain.ask(prompt)).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM healing fail: %s", exc)
            return None

        if not answer or "NAHI_MILA" in answer.upper():
            return None

        # LLM ka batayaa element sach mein screen pe hai?
        answer = answer.strip().strip('"').strip("'")
        match = next(
            (el for el in elements if el.label.lower() == answer.lower()), None
        )
        if match is None:
            match = next(
                (el for el in elements if answer.lower() in el.label.lower()), None
            )
        if match is None:
            return None

        # Naye target pe tap karo
        call = ToolCall(
            id="heal_llm", name="text_pe_tap", arguments={"text": match.label}
        )
        result = await self.registry.execute(call, ctx)

        if not result.ok:
            return None

        # SKILL KO PERMANENTLY THEEK KARO — agli baar seedha chalegi
        old_target = step.target_text
        step.target_text = match.label
        step.target_coords = match.center
        if "text" in step.params:
            step.params["text"] = match.label
        step.notes = f"healed: '{old_target}' -> '{match.label}'"

        log.info("LLM healing safal: '%s' -> '%s'", old_target, match.label)

        return StepOutcome(
            step=step,
            ok=True,
            message=result.output,
            healed=True,
            heal_method=f"LLM ne dhoondha ('{old_target}' -> '{match.label}')",
        )
