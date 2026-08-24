"""
PILLAR #2 — Dikha Do Mode aur 3-level SELF-HEALING.

Yeh project ka killer feature hai. Normal automation (Tasker, macros)
coordinates pe chalta hai — app update aaya, button hila, automation
toot gaya. SAARTHI screen padh ke naya button dhoondh leta hai aur
skill ko PERMANENTLY update kar deta hai.

Ye tests fake device se UI CHANGE simulate karte hain — asli phone ki
zarurat nahi.
"""

from __future__ import annotations

import asyncio

from tests.helpers import SaarthiTestCase

from saarthi.devices.base import ActionResult, UIElement
from saarthi.skills.runner import SkillRunner
from saarthi.skills.store import Skill, SkillStep


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeRegistry:
    """
    Tool registry ka fake — record karta hai kaunsa tool kis order mein
    chala. Healing order test karne ke liye yahi chahiye.
    """

    def __init__(self, screen_elements=None, fail_tools=()):
        self.calls = []
        self.screen_elements = screen_elements or []
        self.fail_tools = set(fail_tools)

    async def execute(self, call, ctx):
        self.calls.append((call.name, dict(call.arguments)))

        if call.name == "screen_padho":
            return ActionResult.success(
                "screen padh liya",
                elements=self.screen_elements,
                interactive=self.screen_elements,
            )

        if call.name in self.fail_tools:
            return ActionResult.failure(f"{call.name} fail hua")

        return ActionResult.success(f"{call.name} ho gaya")

    @property
    def tool_order(self):
        return [name for name, _ in self.calls]


class FakeStore:
    def __init__(self):
        self.saved = []
        self.runs = []

    async def mark_run(self, name, ok):
        self.runs.append((name, ok))

    async def save(self, skill, auto_parameterize=True):
        self.saved.append(skill)


class FakeBrain:
    """LLM ka fake — semantic healing test karne ke liye."""

    def __init__(self, answer="Bijli Bill"):
        self.answer = answer
        self.asked = []

    async def ask(self, prompt, system=None):
        self.asked.append(prompt)
        return self.answer


class FakeDevices:
    def __init__(self, can_read_screen=True):
        self._can = can_read_screen

    def with_capability(self, capability):
        return ["fake-device"] if self._can else []


class FakeCtx:
    def __init__(self, can_read_screen=True, approve=True):
        self.devices = FakeDevices(can_read_screen)
        self.approve = approve
        self.confirmations = []

    async def ask_confirmation(self, action, details=None):
        self.confirmations.append((action, details))
        return self.approve


def make_skill(target_text="Electricity Bill", coords=(500, 900)):
    return Skill(
        name="bijli ka bill",
        steps=[
            SkillStep(
                action="text_pe_tap",
                params={"text": target_text},
                target_text=target_text,
                target_coords=coords,
            )
        ],
    )


class Level1NormalRun(SaarthiTestCase):
    """Step chal gaya to healing ki zarurat nahi."""

    def test_step_chalta_hai_to_healing_nahi_hoti(self):
        registry = FakeRegistry()
        runner = SkillRunner(registry, FakeStore(), FakeBrain())
        result = run(runner.run(make_skill(), {}, FakeCtx()))

        self.assertTrue(result.ok)
        self.assertEqual(result.heal_count, 0)
        self.assertEqual(registry.tool_order, ["text_pe_tap"])

    def test_stats_update_hote_hain(self):
        store = FakeStore()
        runner = SkillRunner(FakeRegistry(), store, FakeBrain())
        run(runner.run(make_skill(), {}, FakeCtx()))
        self.assertEqual(store.runs, [("bijli ka bill", True)])


class Level2SemanticHealing(SaarthiTestCase):
    """
    Text na mila -> screen padho, LLM se pucho, naya target dhoondho,
    aur skill PERMANENTLY update kar do.

    Yahi wo cheez hai jo research papers mein hai par kisi phone agent
    product mein shipped nahi hai.
    """

    def test_ui_badalne_pe_llm_se_naya_button_dhoondhta_hai(self):
        # App update ho gaya: "Electricity Bill" ab "Bijli Bill" hai
        screen = [
            UIElement(text="Bijli Bill", clickable=True, bounds=(100, 200, 300, 250)),
            UIElement(text="Mobile Recharge", clickable=True, bounds=(100, 300, 300, 350)),
        ]
        registry = FakeRegistry(screen_elements=screen, fail_tools=())
        # Pehla text_pe_tap fail karao, healing ke baad wala pass ho
        original_execute = registry.execute
        state = {"first": True}

        async def execute(call, ctx):
            if call.name == "text_pe_tap" and state["first"]:
                state["first"] = False
                registry.calls.append((call.name, dict(call.arguments)))
                return ActionResult.failure("element nahi mila")
            return await original_execute(call, ctx)

        registry.execute = execute

        brain = FakeBrain(answer="Bijli Bill")
        store = FakeStore()
        skill = make_skill()
        result = run(SkillRunner(registry, store, brain).run(skill, {}, FakeCtx()))

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.heal_count, 1)
        self.assertTrue(brain.asked, "LLM se poocha hi nahi")

        # Skill PERMANENTLY update honi chahiye — agli baar seedha chale
        self.assertEqual(skill.steps[0].target_text, "Bijli Bill")
        self.assertTrue(store.saved, "healed skill save nahi hui")
        self.assertIn("healed", skill.steps[0].notes)

    def test_screen_padhne_ke_baad_llm_ko_options_milte_hain(self):
        screen = [UIElement(text="Bijli Bill", clickable=True, bounds=(0, 0, 10, 10))]
        registry = FakeRegistry(screen_elements=screen)
        state = {"first": True}
        original = registry.execute

        async def execute(call, ctx):
            if call.name == "text_pe_tap" and state["first"]:
                state["first"] = False
                registry.calls.append((call.name, {}))
                return ActionResult.failure("nahi mila")
            return await original(call, ctx)

        registry.execute = execute
        brain = FakeBrain()
        run(SkillRunner(registry, FakeStore(), brain).run(make_skill(), {}, FakeCtx()))

        self.assertIn("screen_padho", registry.tool_order)
        self.assertIn("Bijli Bill", brain.asked[0])

    def test_llm_ka_jawab_screen_pe_na_ho_to_maanta_nahi(self):
        """LLM hallucinate kare to blindly follow nahi karna."""
        screen = [UIElement(text="Mobile Recharge", clickable=True, bounds=(0, 0, 5, 5))]
        registry = FakeRegistry(screen_elements=screen, fail_tools=("text_pe_tap",))
        brain = FakeBrain(answer="Kuch Aur Hi Button")
        ctx = FakeCtx(approve=False)

        result = run(SkillRunner(registry, FakeStore(), brain).run(make_skill(), {}, ctx))
        self.assertFalse(result.ok)


class Level3CoordinatesLastResort(SaarthiTestCase):
    """
    Coordinates SABSE AAKHIR, aur wo bhi permission ke saath.

    Kyun: text na mila = UI badal gaya. Purane coordinates pe tap karna
    galat button daba sakta hai. Payment screen pe bahut bura.
    """

    def test_screen_padh_sakte_hain_to_permission_maangta_hai(self):
        registry = FakeRegistry(screen_elements=[], fail_tools=("text_pe_tap",))
        ctx = FakeCtx(can_read_screen=True, approve=True)
        result = run(SkillRunner(registry, FakeStore(), FakeBrain()).run(
            make_skill(), {}, ctx
        ))

        self.assertTrue(ctx.confirmations, "Blind coordinate tap se pehle poocha nahi!")
        self.assertTrue(result.ok)
        self.assertIn("coordinate_pe_tap", registry.tool_order)

    def test_permission_na_mile_to_tap_nahi_karta(self):
        registry = FakeRegistry(screen_elements=[], fail_tools=("text_pe_tap",))
        ctx = FakeCtx(can_read_screen=True, approve=False)
        result = run(SkillRunner(registry, FakeStore(), FakeBrain()).run(
            make_skill(), {}, ctx
        ))

        self.assertFalse(result.ok)
        self.assertNotIn(
            "coordinate_pe_tap",
            registry.tool_order,
            "Mana karne ke baad bhi blind tap kar diya!",
        )

    def test_coordinates_semantic_ke_BAAD_aate_hain(self):
        """BUG#3 ka core — order ulta hua to payment screen pe khatra."""
        registry = FakeRegistry(screen_elements=[], fail_tools=("text_pe_tap",))
        run(SkillRunner(registry, FakeStore(), FakeBrain()).run(
            make_skill(), {}, FakeCtx(can_read_screen=True, approve=True)
        ))

        order = registry.tool_order
        self.assertIn("screen_padho", order)
        self.assertIn("coordinate_pe_tap", order)
        self.assertLess(
            order.index("screen_padho"),
            order.index("coordinate_pe_tap"),
            "Coordinates semantic se PEHLE aa gaye — BUG#3 wapas!",
        )


class SkillParameters(SaarthiTestCase):
    """Placeholders — recorded "2500" ko {amount} banana."""

    def test_zaroori_value_na_ho_to_pehle_hi_ruk_jaata_hai(self):
        """Beech mein fail hone se behtar hai pehle bata dena."""
        skill = Skill(
            name="bill bharo",
            steps=[SkillStep(action="text_likho", params={"text": "{amount}"})],
        )
        result = run(SkillRunner(FakeRegistry(), FakeStore(), FakeBrain()).run(
            skill, {}, FakeCtx()
        ))

        self.assertFalse(result.ok)
        self.assertIn("amount", result.error)

    def test_value_dene_pe_chal_jaata_hai(self):
        skill = Skill(
            name="bill bharo",
            steps=[SkillStep(action="text_likho", params={"text": "{amount}"})],
        )
        registry = FakeRegistry()
        result = run(SkillRunner(registry, FakeStore(), FakeBrain()).run(
            skill, {"amount": 2500}, FakeCtx()
        ))

        self.assertTrue(result.ok, result.error)
        # Type preserve hota hai (int 2500, str "2500" nahi) — ye
        # jaan-boojh ke hai, BUG#2 isi se aaya tha. Tool ka
        # coerce_args() baad mein sahi type bana leta hai.
        self.assertEqual(str(registry.calls[0][1]["text"]), "2500")


class BothTargetsStored(SaarthiTestCase):
    """
    Har step DONO target rakhta hai: target_text (primary) aur
    target_coords (fallback). Yahi self-healing ki foundation hai.
    """

    def test_step_dono_target_rakhta_hai(self):
        step = SkillStep(
            action="text_pe_tap",
            params={"text": "Pay"},
            target_text="Pay",
            target_coords=(100, 200),
        )
        self.assertEqual(step.target_text, "Pay")
        self.assertEqual(step.target_coords, (100, 200))

    def test_report_padhne_layak_hai(self):
        registry = FakeRegistry()
        result = run(SkillRunner(registry, FakeStore(), FakeBrain()).run(
            make_skill(), {}, FakeCtx()
        ))
        report = result.report()
        self.assertIn("bijli ka bill", report)
