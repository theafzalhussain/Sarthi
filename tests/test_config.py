"""
Config — 8 providers, capabilities, aur env overrides.

Khaas dhyan: ek NVIDIA key se 4 models chalte hain. Wo wiring toot
jaaye to user ko lagega "naya model kaam nahi kar raha".
"""

from __future__ import annotations

from tests.helpers import SaarthiTestCase, clean_env

from saarthi.brain.openai_compat import BASE_URLS
from saarthi.config import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER_ORDER,
    NVIDIA_HOSTED,
    Settings,
)

NVIDIA_NIM = "https://integrate.api.nvidia.com/v1"


class Providers(SaarthiTestCase):
    def test_8_providers_hain(self):
        with clean_env():
            self.assertEqual(len(Settings.load().providers), 8)

    def test_saare_providers_ka_base_url_hai(self):
        for name in DEFAULT_MODELS:
            if name == "gemini":
                continue  # Gemini ka apna client hai, BASE_URLS mein nahi
            self.assertIn(name, BASE_URLS, f"'{name}' ka base URL nahi mila")

    def test_default_models_sahi_hain(self):
        expected = {
            "deepseek": "deepseek-ai/deepseek-v4-pro",
            "muse": "meta/muse-glimmer-30b",
            "gemma": "google/diffusiongemma-26b-a4b-it",
            "nvidia": "nvidia/nemotron-3-ultra-550b-a55b",
            "groq": "openai/gpt-oss-20b",
            "gemini": "gemini-3.6-flash",
        }
        for name, model in expected.items():
            self.assertEqual(DEFAULT_MODELS[name], model, f"'{name}' ka model badal gaya")

    def test_nvidia_hosted_saare_same_endpoint_pe_hain(self):
        for name in NVIDIA_HOSTED:
            self.assertEqual(BASE_URLS[name], NVIDIA_NIM, f"'{name}' galat URL pe hai")


class OneKeyFourModels(SaarthiTestCase):
    """
    Ek NVIDIA key = 4 models. Ye wiring bahut kaam ki hai — free tier
    pe 4 fallback slots mil jaate hain.
    """

    def test_ek_nvidia_key_se_chaar_providers_available_hote_hain(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake"):
            available = {p.name for p in Settings.load().available_providers}
        self.assertEqual(available, set(NVIDIA_HOSTED))

    def test_chaaron_wahi_key_uthate_hain(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake"):
            for provider in Settings.load().available_providers:
                self.assertEqual(provider.api_key, "nvapi-fake", provider.name)

    def test_nvidia_nim_api_key_bhi_chalti_hai(self):
        with clean_env(NVIDIA_NIM_API_KEY="nvapi-alt"):
            available = {p.name for p in Settings.load().available_providers}
        self.assertEqual(available, set(NVIDIA_HOSTED))

    def test_alag_key_di_jaaye_to_wo_priority_leti_hai(self):
        with clean_env(NVIDIA_API_KEY="nvapi-shared", DEEPSEEK_API_KEY="nvapi-own"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertEqual(providers["deepseek"].api_key, "nvapi-own")
        self.assertEqual(providers["nvidia"].api_key, "nvapi-shared")


class Capabilities(SaarthiTestCase):
    """
    tools/vision flags. Ye AUTO-DETECT nahi hote, isliye test zaroori
    hai — galat flag se agent chup-chaap fail karega.
    """

    def caps(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake"):
            return {p.name: p for p in Settings.load().available_providers}

    def test_capabilities_sahi_hain(self):
        expected = {
            # name:      (tools, vision)
            "nvidia": (True, False),
            "deepseek": (True, False),
            "muse": (True, True),    # multimodal + native tool calling
            "gemma": (False, True),  # diffusion -> tools bharosemand nahi
        }
        providers = self.caps()
        for name, (tools, vision) in expected.items():
            self.assertIs(providers[name].supports_tools, tools, f"{name} tools")
            self.assertIs(providers[name].supports_vision, vision, f"{name} vision")

    def test_gemma_ke_tools_default_off_hain(self):
        """Diffusion model hai — verify nahi hua, isliye safe default."""
        self.assertFalse(self.caps()["gemma"].supports_tools)

    def test_deepseek_thinking_off_karta_hai(self):
        self.assertEqual(
            self.caps()["deepseek"].extra_body,
            {"chat_template_kwargs": {"thinking": False}},
        )

    def test_env_se_capability_override_ho_sakti_hai(self):
        with clean_env(
            NVIDIA_API_KEY="nvapi-fake", GEMMA_TOOLS="true", MUSE_VISION="false"
        ):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertTrue(providers["gemma"].supports_tools)
        self.assertFalse(providers["muse"].supports_vision)


class ProviderOrder(SaarthiTestCase):
    def test_best_pehle_hai(self):
        self.assertEqual(DEFAULT_PROVIDER_ORDER[0], "deepseek")

    def test_gemma_aakhir_mein_hai(self):
        """Tools bharosemand nahi — sabse aakhir."""
        self.assertEqual(DEFAULT_PROVIDER_ORDER[-1], "gemma")

    def test_8_providers_order_mein_hain(self):
        self.assertEqual(len(DEFAULT_PROVIDER_ORDER), 8)
        self.assertEqual(len(set(DEFAULT_PROVIDER_ORDER)), 8, "duplicate hai")

    def test_env_se_order_badal_sakta_hai(self):
        with clean_env(
            NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="muse,deepseek"
        ):
            order = Settings.load().provider_order
        self.assertEqual(order[:2], ["muse", "deepseek"])

    def test_purana_order_detect_hota_hai(self):
        """
        CHUP-CHAAP TRAP: user ne purana order likha tha (jab 5 providers
        the). Naye models us list mein nahi the, isliye wo SABSE AAKHIR
        chale gaye — chahe wo sabse smart hon. User ko pata bhi nahi
        chalta. Isliye startup pe warning dikhate hain.
        """
        with clean_env(
            NVIDIA_API_KEY="nvapi-fake",
            SAARTHI_PROVIDER_ORDER="bluesminds,nvidia,gemini,openrouter,groq",
        ):
            settings = Settings.load()

        self.assertTrue(settings.order_is_explicit)
        self.assertEqual(set(settings.order_missing), {"deepseek", "muse", "gemma"})
        self.assertEqual(settings.provider_order[-3:], ["deepseek", "muse", "gemma"])

    def test_bina_env_ke_explicit_flag_off_rehta_hai(self):
        with clean_env():
            settings = Settings.load()
        self.assertFalse(settings.order_is_explicit)
        self.assertEqual(settings.order_missing, [])


class BehaviourSettings(SaarthiTestCase):
    def test_defaults(self):
        with clean_env():
            settings = Settings.load()
        self.assertEqual(settings.language, "auto")
        self.assertEqual(settings.max_steps, 25)
        self.assertEqual(settings.browser_mode, "auto")
        self.assertFalse(settings.browser_headless)
        self.assertTrue(settings.confirm_risky, "confirm_risky default ON hona chahiye")
        self.assertFalse(settings.auto_approve, "auto_approve default OFF hona chahiye")

    def test_language_choices(self):
        for value in ("auto", "hinglish", "english", "hindi"):
            with clean_env(SAARTHI_LANGUAGE=value):
                self.assertEqual(Settings.load().language, value)

    def test_galat_value_pe_default_pe_gir_jaata_hai(self):
        """Crash karna bekaar hai — galat value pe agent rukna nahi chahiye."""
        with clean_env(SAARTHI_LANGUAGE="bakwaas"):
            self.assertEqual(Settings.load().language, "auto")
        with clean_env(SAARTHI_BROWSER_MODE="bakwaas"):
            self.assertEqual(Settings.load().browser_mode, "auto")

    def test_max_steps_env_se_badal_sakta_hai(self):
        with clean_env(SAARTHI_MAX_STEPS="15"):
            self.assertEqual(Settings.load().max_steps, 15)

    def test_galat_max_steps_pe_default(self):
        with clean_env(SAARTHI_MAX_STEPS="bakwaas"):
            self.assertEqual(Settings.load().max_steps, 25)

    def test_auto_approve_env_se_on_ho_sakta_hai(self):
        with clean_env(SAARTHI_AUTO_APPROVE="true"):
            self.assertTrue(Settings.load().auto_approve)

    def test_setup_help_actionable_hai(self):
        with clean_env():
            help_text = Settings.load().setup_help()
        self.assertIn("build.nvidia.com", help_text)
        self.assertIn(".env", help_text)

    def test_koi_key_na_ho_to_has_any_provider_false(self):
        with clean_env():
            self.assertFalse(Settings.load().has_any_provider)
