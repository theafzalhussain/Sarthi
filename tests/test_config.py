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
            self.assertEqual(len(Settings.load().providers), 9)

    def test_saare_providers_ka_base_url_hai(self):
        for name in DEFAULT_MODELS:
            if name == "gemini":
                continue  # Gemini ka apna client hai, BASE_URLS mein nahi
            self.assertIn(name, BASE_URLS, f"'{name}' ka base URL nahi mila")

    def test_default_models_sahi_hain(self):
        expected = {
            "deepseek": "deepseek-ai/deepseek-v4-pro-0813",
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

    def test_provider_order_mein_duplicate_nahi_hai(self):
        """
        Ginti hardcode karna band — pehle ye test "8_providers" tha aur
        `opencode` add hone pe aadha update hua: naam 8 kehta tha, len
        9 assert karta tha, aur set 8. Confusing aur bekaar.

        Asli baat ye hai: koi DUPLICATE na ho (warna ek provider do baar
        try hoga) aur order mein har provider ka config maujood ho.
        """
        self.assertEqual(
            len(DEFAULT_PROVIDER_ORDER), len(set(DEFAULT_PROVIDER_ORDER)),
            "provider order mein duplicate hai",
        )
        self.assertGreaterEqual(len(DEFAULT_PROVIDER_ORDER), 8)

    def test_order_ka_har_provider_ka_model_defined_hai(self):
        """
        Naya provider order mein daala par DEFAULT_MODELS mein bhoola —
        to wo runtime pe KeyError ya khali model dega. Ye chup-chaap
        fail hone wali cheez hai.
        """
        from saarthi.config import DEFAULT_MODELS

        for name in DEFAULT_PROVIDER_ORDER:
            with self.subTest(provider=name):
                self.assertIn(
                    name, DEFAULT_MODELS,
                    f"'{name}' order mein hai par DEFAULT_MODELS mein nahi",
                )
                self.assertTrue(DEFAULT_MODELS[name], f"'{name}' ka model khali hai")

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

        # Jo user ki list mein nahi the wo missing hone chahiye — ginti
        # hardcode nahi karte, DEFAULT_PROVIDER_ORDER se nikalte hain
        # taaki naya provider add hone pe test stale na ho.
        listed = {"bluesminds", "nvidia", "gemini", "openrouter", "groq"}
        expected_missing = [p for p in DEFAULT_PROVIDER_ORDER if p not in listed]

        self.assertEqual(set(settings.order_missing), set(expected_missing))

        # Aur missing wale AAKHIR mein jaate hain, default order mein
        self.assertEqual(
            settings.provider_order[-len(expected_missing):], expected_missing,
            "missing providers aakhir mein default order se nahi lage",
        )

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



class GenerationTuning(SaarthiTestCase):
    """
    BUG#11 — .env ki generation settings KUCH NAHI KARTI THI.

    User ki .env mein ye tha:
        NVIDIA_ENABLE_THINKING=true
        NVIDIA_MAX_TOKENS=16384
        NVIDIA_TOP_P=0.95

    Teeno env vars CODE MEIN HI NAHI THE. User ko lagta raha ki setting
    kaam kar rahi hai, jabki kuch nahi ho raha tha.

    Aur `max_tokens` har jagah 2048 hardcoded tha — reasoning model ke
    saath thinking ON ho to jawab BEECH MEIN KAT jaata hai, kyunki
    reasoning tokens bhi usi budget se khaate hain.
    """

    def test_global_max_tokens_default_4096_hai(self):
        with clean_env():
            self.assertEqual(Settings.load().max_tokens, 4096)

    def test_global_max_tokens_env_se_badalta_hai(self):
        with clean_env(SAARTHI_MAX_TOKENS="8192"):
            self.assertEqual(Settings.load().max_tokens, 8192)

    def test_per_provider_max_tokens_chalta_hai(self):
        with clean_env(NVIDIA_API_KEY="x", NVIDIA_MAX_TOKENS="16384"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertEqual(providers["nvidia"].max_tokens, 16384)
        self.assertIsNone(providers["muse"].max_tokens, "muse ko nahi lagna chahiye")

    def test_per_provider_top_p_chalta_hai(self):
        with clean_env(NVIDIA_API_KEY="x", NVIDIA_TOP_P="0.95"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertEqual(providers["nvidia"].top_p, 0.95)
        self.assertIsNone(providers["gemma"].top_p)

    def test_enable_thinking_true_extra_body_mein_jaata_hai(self):
        with clean_env(NVIDIA_API_KEY="x", NVIDIA_ENABLE_THINKING="true"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertEqual(
            providers["nvidia"].extra_body,
            {"chat_template_kwargs": {"thinking": True}},
        )

    def test_enable_thinking_deepseek_ka_default_override_kar_sakta_hai(self):
        """DeepSeek ka default thinking=False hai — user on kar sake."""
        with clean_env(NVIDIA_API_KEY="x"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertFalse(providers["deepseek"].extra_body["chat_template_kwargs"]["thinking"])

        with clean_env(NVIDIA_API_KEY="x", DEEPSEEK_ENABLE_THINKING="true"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertTrue(providers["deepseek"].extra_body["chat_template_kwargs"]["thinking"])

    def test_galat_value_pe_setting_ignore_hoti_hai_crash_nahi(self):
        with clean_env(
            NVIDIA_API_KEY="x", NVIDIA_MAX_TOKENS="bakwaas", NVIDIA_TOP_P="bakwaas"
        ):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertIsNone(providers["nvidia"].max_tokens)
        self.assertIsNone(providers["nvidia"].top_p)

    def test_set_na_ho_to_none_rehta_hai(self):
        """None = provider ka apna default. Payload mein bhejte hi nahi."""
        with clean_env(NVIDIA_API_KEY="x"):
            providers = {p.name: p for p in Settings.load().available_providers}
        self.assertIsNone(providers["nvidia"].max_tokens)
        self.assertIsNone(providers["nvidia"].top_p)


class DefaultDeviceValidation(SaarthiTestCase):
    """
    BUG#12 — SAARTHI_DEFAULT_DEVICE pe koi validation nahi thi.

    User ne galti se `SAARTHI_DEFAULT_DEVICE=Realtek` likh diya tha
    (mic ki setting samajh ke — asli setting SAARTHI_MIC_DEVICE hai).

    Bina validation wo chup-chaap accept ho gaya. Ittefaq se desktop pe
    gir jaata tha (kyunki DeviceManager.get() None pe pehla device leta
    hai), par wo LUCK thi, design nahi.
    """

    def test_valid_device_chalta_hai(self):
        for value in ("desktop", "android", "browser"):
            with clean_env(SAARTHI_DEFAULT_DEVICE=value):
                self.assertEqual(Settings.load().default_device, value)

    def test_galat_value_desktop_pe_girti_hai(self):
        for value in ("Realtek", "Microphone Array", "bakwaas", ""):
            with clean_env(SAARTHI_DEFAULT_DEVICE=value):
                self.assertEqual(
                    Settings.load().default_device,
                    "desktop",
                    f"{value!r} pe desktop nahi mila",
                )

    def test_case_insensitive_hai(self):
        with clean_env(SAARTHI_DEFAULT_DEVICE="ANDROID"):
            self.assertEqual(Settings.load().default_device, "android")


class InlineComments(SaarthiTestCase):
    """
    User ki .env mein inline comment tha:
        SAARTHI_BROWSER_MODE=auto        # auto | agent | system

    python-dotenv ise strip kar deta hai, par bharosa nahi karna
    chahiye. `_env_choice` ki validation isliye bhi bachati hai — comment
    strip na ho to value invalid ban jaayegi aur default pe gir jaayegi,
    crash nahi hoga.
    """

    def test_comment_strip_na_ho_to_bhi_safe_default_milta_hai(self):
        with clean_env(SAARTHI_BROWSER_MODE="auto        # auto | agent | system"):
            self.assertEqual(Settings.load().browser_mode, "auto")

    def test_valid_value_ke_saath_comment_bhi_chalta_hai(self):
        with clean_env(SAARTHI_BROWSER_MODE="agent"):
            self.assertEqual(Settings.load().browser_mode, "agent")



class EnvExampleMatchesCode(SaarthiTestCase):
    """
    `.env.example` mein likhe MODEL NAAM code ke default se match karein.

    ⚠️ YE EK ASLI BUG SE BANA HAI.

    `deepseek-ai/deepseek-v4-pro` 2026-08-07 pe EOL ho gaya. Code mein
    `-0813` version aa gaya, par `.env.example` mein purana naam commented
    pada reh gaya:

        # DEEPSEEK_MODEL=deepseek-ai/deepseek-v4-pro

    Ye SABSE KHATARNAK kism ka stale doc hai — user us line ko uncomment
    karta hai (bilkul wajib kaam), aur usko 404 milta hai. Wo samjhega
    agent tuta hua hai, jabki usne bas hamara apna example follow kiya.

    BUG#6 bhi exactly yahi tha (deprecated model names, teen provider 404
    de rahe the). Isliye ab test isko pakadta hai.
    """

    def env_example_models(self) -> dict:
        """`.env.example` se `{PROVIDER}_MODEL=value` nikaalo (commented bhi)."""
        import re

        from saarthi.config import ROOT_DIR

        path = ROOT_DIR / ".env.example"
        self.assertTrue(path.exists(), ".env.example gayab hai")

        found = {}
        pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9]*)_MODEL\s*=\s*(\S+)\s*$")
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                found.setdefault(match.group(1).lower(), match.group(2))
        return found

    def test_env_example_mein_kuch_model_line_hai(self):
        """Parser hi toota ho to baaki test jhoothe pass ho jaayenge."""
        self.assertGreater(
            len(self.env_example_models()), 3,
            "koi *_MODEL line nahi mili — parser check kar",
        )

    def test_env_example_ke_model_naam_code_se_match_karte_hain(self):
        from saarthi.config import DEFAULT_MODELS

        for provider, model in self.env_example_models().items():
            if provider not in DEFAULT_MODELS:
                continue  # alag/extra example, wo theek hai
            with self.subTest(provider=provider):
                self.assertEqual(
                    model, DEFAULT_MODELS[provider],
                    f"\n.env.example mein {provider.upper()}_MODEL={model}\n"
                    f"par code ka default   {DEFAULT_MODELS[provider]}\n"
                    f"User us line ko uncomment karega to 404 milega.",
                )
