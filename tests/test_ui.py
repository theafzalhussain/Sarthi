"""
UI layer — render crash na kare, aur interface ENGLISH mein rahe.

Ye tests isliye hain kyunki ek asli bug aisa mila tha:
`registry.names` property hai par UI code use `names()` method ki tarah
call kar raha tha. Wo bug SIRF tab pakda gaya jab `/tools` chalaya.
Renderers ka smoke test us class ke bugs pakad leta hai.
"""

from __future__ import annotations

import asyncio
import pathlib

from tests.helpers import SaarthiTestCase, captured_stdout, clean_env

from saarthi.brain import Brain
from saarthi.config import Settings
from saarthi.devices import DeviceManager
from saarthi.tools import default_registry
from saarthi.ui import Ui

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeProvider:
    def __init__(self, name, model, vision=False, tools=True):
        self.name = name
        self.model = model
        self.supports_vision = vision
        self.supports_tools = tools


class FakeBrain:
    def __init__(self, providers=None, health=None):
        # `providers or [...]` MAT likhna — khali list bhi falsy hai,
        # to `providers=[]` pass karne pe default aa jaata hai.
        # Classic Python gotcha, aur ek test isi se fail hua tha.
        if providers is None:
            providers = [
                FakeProvider("deepseek", "deepseek-ai/deepseek-v4-pro"),
                FakeProvider("muse", "meta/muse-glimmer-30b", vision=True),
                FakeProvider("gemma", "google/diffusiongemma-26b-a4b-it",
                             vision=True, tools=False),
            ]
        self.providers = providers
        self._health = health if health is not None else {}

    def health(self):
        return self._health


class Renderers(SaarthiTestCase):
    """Har renderer chalna chahiye — crash nahi."""

    def setUp(self):
        self.ui = Ui(plain=True)

    def render(self, fn):
        with captured_stdout() as out:
            fn()
        return out.getvalue()

    def test_banner(self):
        self.assertTrue(self.render(lambda: self.ui.banner("0.1.0", "tagline", "mode")))

    def test_section_aur_rule(self):
        self.assertIn("BRAIN", self.render(lambda: self.ui.section("Brain")))
        self.assertTrue(self.render(self.ui.rule))

    def test_messages(self):
        for fn in (
            lambda: self.ui.info("info"),
            lambda: self.ui.muted("muted"),
            lambda: self.ui.success("ok"),
            lambda: self.ui.warn("warn"),
            lambda: self.ui.error("err"),
            lambda: self.ui.hint("line1\nline2", title="note"),
            lambda: self.ui.block("a\nb"),
        ):
            self.assertTrue(self.render(fn))

    def test_table(self):
        output = self.render(
            lambda: self.ui.table(["a", "b"], [["1", "2"], ["3", "4"]])
        )
        self.assertIn("1", output)
        self.assertIn("4", output)

    def test_khali_table_crash_nahi_karta(self):
        self.render(lambda: self.ui.table(["a"], []))

    def test_reply_aur_error(self):
        self.assertIn("hi", self.render(lambda: self.ui.reply("**hi** bhai", meta="1 step")))
        self.assertTrue(self.render(lambda: self.ui.reply_error("kuch galat")))

    def test_activity_har_kind_ke_liye(self):
        for kind in ("thinking", "tool", "result", "error", "debug", "unknown"):
            self.assertTrue(self.render(lambda k=kind: self.ui.activity(k, "text")))

    def test_prompt_aur_badge(self):
        self.assertIn("you", self.ui.prompt("you"))
        self.assertTrue(self.ui.badge(True))
        self.assertTrue(self.ui.badge(False))

    def test_brain_table(self):
        output = self.render(lambda: self.ui.brain_table(FakeBrain()))
        self.assertIn("deepseek", output)
        self.assertIn("gemma", output)

    def test_brain_table_dead_provider_dikhata_hai(self):
        brain = FakeBrain(health={"deepseek": "dead: model enable nahi hai",
                                  "muse": "ok", "gemma": "ok"})
        output = self.render(lambda: self.ui.brain_table(brain))
        self.assertIn("HATA DIYA", output)
        self.assertIn("enable nahi hai", output)

    def test_brain_table_cooldown_dikhata_hai(self):
        brain = FakeBrain(health={"deepseek": "cooldown: 42s", "muse": "ok", "gemma": "ok"})
        self.assertIn("cooldown", self.render(lambda: self.ui.brain_table(brain)))

    def test_khali_brain_pe_saaf_message(self):
        output = self.render(lambda: self.ui.brain_table(FakeBrain(providers=[])))
        self.assertIn("No provider", output)

    def test_tools_table(self):
        """
        Ye test us asli bug ko pakadta hai jahan `registry.names`
        property ko method ki tarah call kiya gaya tha.
        """
        output = self.render(lambda: self.ui.tools_table(default_registry()))
        self.assertIn("app_kholo", output)
        self.assertIn("website_kholo", output)

    def test_devices_table_dono_mode_mein(self):
        with clean_env(GROQ_API_KEY="fake"):
            settings = Settings.load()
        manager = DeviceManager(settings)
        manager.setup_defaults()
        status = run(manager.check_availability())

        for detailed in (False, True):
            output = self.render(
                lambda d=detailed: self.ui.devices_table(manager, status, detailed=d)
            )
            self.assertIn("desktop", output)

    def test_devices_table_hints_deta_hai(self):
        with clean_env(GROQ_API_KEY="fake"):
            settings = Settings.load()
        manager = DeviceManager(settings)
        manager.setup_defaults()
        status = run(manager.check_availability())

        with captured_stdout():
            hints = self.ui.devices_table(manager, status)
        for name, hint in hints:
            self.assertTrue(hint.strip(), f"'{name}' ka hint khali hai")


class Degradation(SaarthiTestCase):
    """
    Architecture rule: optional dependency crash nahi karati.

    rich na ho ya terminal unicode na kare to plain ASCII pe chalna
    chahiye — purana Windows terminal, SSH, log file, sab.
    """

    def test_ascii_mode_chalta_hai(self):
        with clean_env(SAARTHI_ASCII_UI="1"):
            ui = Ui()
            with captured_stdout() as out:
                ui.banner("0.1.0", "t")
                ui.table(["a"], [["1"]])
                ui.reply("hi")
                ui.brain_table(FakeBrain())
            self.assertTrue(out.getvalue())

    def test_plain_mode_chalta_hai(self):
        ui = Ui(plain=True)
        self.assertFalse(ui.rich)
        with captured_stdout() as out:
            ui.banner("0.1.0", "t")
            ui.reply("hi", meta="x")
            ui.hint("note")
        self.assertTrue(out.getvalue())

    def test_ascii_mode_mein_fancy_symbol_nahi_hote(self):
        with clean_env(SAARTHI_ASCII_UI="1"):
            ui = Ui()
            for value in ui.sym.values():
                self.assertTrue(
                    value.isascii(), f"ASCII mode mein non-ascii symbol: {value!r}"
                )

    def test_80_column_ka_khayal_rakhta_hai(self):
        self.assertLessEqual(Ui(plain=True).width, 84)


class InterfaceEnglish(SaarthiTestCase):
    """
    Interface ENGLISH mein hona chahiye (professional), par agent ki
    BAAT user ki bhasha mein.

    Ye do alag cheezein hain — is test se dono confuse na ho.
    """

    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_ui_ke_column_headers_english_hain(self):
        source = self.read("saarthi/ui.py")
        for header in ('"vision"', '"capabilities"', '"purpose"'):
            self.assertIn(header, source, f"English header gayab: {header}")
        for old in ('"aankh"', '"kya kar sakta hai"', '"kaam"]'):
            self.assertNotIn(old, source, f"Purana Hinglish header wapas: {old}")

    def test_prompt_label_english_hai(self):
        self.assertIn('label: str = "you"', self.read("saarthi/ui.py"))

    def test_cli_ke_messages_english_hain(self):
        source = self.read("cli.py")
        for text in (
            "approve? y / n", "How to use", "Goodbye.",
            "confirmation required", "Unknown command", "reply language",
        ):
            self.assertIn(text, source, f"English string gayab: {text!r}")

    def test_purane_hinglish_ui_strings_hat_gaye(self):
        source = self.read("cli.py")
        for old in (
            'ui.error("cancel kar diya")',
            'ui.success("theek hai, kar raha hun")',
            "Ready hun bhai. Bol kya karna hai.",
            "Chalo bye! Phir milte hain.",
        ):
            self.assertNotIn(old, source, f"Purana Hinglish UI string wapas: {old}")

    def test_voice_cli_ke_messages_english_hain(self):
        source = self.read("voice_cli.py")
        for text in ("Result", "All set. Run:", "Goodbye.", "Listening.", "Heard:"):
            self.assertIn(text, source, f"English string gayab: {text!r}")

    def test_agent_ki_baat_hinglish_reh_sakti_hai(self):
        """
        Interface English hua, par Hinglish REPLY rules zinda hone
        chahiye — wahi Pillar #1 hai.
        """
        from saarthi.lang.prompts import LANGUAGE_RULES

        self.assertIn("auto", LANGUAGE_RULES)
        self.assertIn("hinglish", LANGUAGE_RULES)
        self.assertIn("roman script", LANGUAGE_RULES["auto"])
        self.assertIn("MIRROR THE USER", LANGUAGE_RULES["auto"])


class RealObjects(SaarthiTestCase):
    """Asli Brain object ke saath bhi render hona chahiye."""

    def test_asli_brain_render_hota_hai(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake"):
            brain = Brain(Settings.load())
        ui = Ui(plain=True)
        with captured_stdout() as out:
            ui.brain_table(brain)
        output = out.getvalue()
        self.assertIn("deepseek", output)
        self.assertIn("muse", output)
