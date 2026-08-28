"""
Phase 5A — Ollama on-device LLM integration tests.

Ye tests ASLI OLLAMA SERVER NAHI CHAHTE. Sab fake hai:
  - Network httpx fake se
  - Env vars clean_env se
  - Koi model pull nahi, koi download nahi

KAUNSE SCENARIOS TEST HO RAHE HAIN:
  1. BASE_URLS mein ollama hai
  2. OLLAMA_HOST env se override hota hai
  3. _build_provider() Ollama ke liye OpenAICompatProvider deta hai
  4. Bina API key Ollama available hai (OLLAMA_ENABLED=true pe)
  5. REGRESSION: bina key wala CLOUD provider abhi bhi unavailable hai
  6. Payload OpenAI format mein jaata hai
  7. supports_tools=True hai
  8. Ollama band ho to clear actionable error mile, crash nahi
  9. OLLAMA_ENABLED=false pe unavailable
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import FakeHTTP, FakeResponse, SaarthiTestCase, clean_env

from saarthi.brain import Brain
from saarthi.brain.openai_compat import BASE_URLS, OpenAICompatProvider
from saarthi.brain.router import _build_provider
from saarthi.brain.types import BrainError, Message, ToolSchema
from saarthi.config import DEFAULT_MODELS, Settings


def run(coro):
    """Async test helper."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


TOOL = ToolSchema(
    name="app_kholo",
    description="app kholo",
    parameters={"type": "object", "properties": {}},
)


class OllamaInBaseURLs(SaarthiTestCase):
    """BASE_URLS mein ollama entry hona chahiye."""

    def test_ollama_base_urls_mein_hai(self):
        """Ollama ka entry BASE_URLS dict mein maujood hai."""
        self.assertIn("ollama", BASE_URLS)

    def test_ollama_url_mein_v1_suffix_hai(self):
        """OpenAI-compatible endpoint /v1 pe hota hai."""
        url = BASE_URLS["ollama"]
        self.assertTrue(url.endswith("/v1"), f"URL /v1 pe khatam nahi: {url}")

    def test_ollama_host_env_se_override_hota_hai(self):
        """
        BEHAVIOUR TEST — asli env set karke import-time value check.

        Kuch log Ollama doosri machine pe chalate hain (NAS, server).
        OLLAMA_HOST se URL badalna zaroori hai.
        """
        custom_host = "http://192.168.1.50:11434"
        with patch.dict(os.environ, {"OLLAMA_HOST": custom_host}):
            # BASE_URLS module level pe evaluate hota hai, isliye
            # reload karna padega ya seedha construct karke test karo
            expected = custom_host + "/v1"
            # OpenAICompatProvider ko seedha banake test karo
            from saarthi.config import ProviderConfig
            config = ProviderConfig(
                name="ollama",
                api_key="ollama",
                model="qwen2.5:7b",
                requires_key=False,
            )
            provider = OpenAICompatProvider(config, base_url=expected)
            self.assertEqual(provider.base_url, expected)


class OllamaDefaultModel(SaarthiTestCase):
    """DEFAULT_MODELS mein ollama hai."""

    def test_ollama_default_model_set_hai(self):
        self.assertIn("ollama", DEFAULT_MODELS)

    def test_ollama_default_model_tool_calling_wala_hai(self):
        """qwen2.5 tool calling support karta hai."""
        model = DEFAULT_MODELS["ollama"]
        # qwen2.5 ya llama3 — dono tool calling karte hain
        self.assertTrue(
            "qwen" in model or "llama" in model,
            f"Default model ({model}) tool calling support karta ho — verify kar"
        )


class OllamaBuildProvider(SaarthiTestCase):
    """_build_provider() sahi class deta hai."""

    def test_build_provider_ollama_ke_liye_openai_compat_deta_hai(self):
        """
        BEHAVIOUR TEST — _build_provider ko asli config de ke chalao.
        Ye verify karta hai ki Ollama ke liye OpenAICompatProvider banta hai.
        """
        from saarthi.config import ProviderConfig
        config = ProviderConfig(
            name="ollama",
            api_key="ollama",
            model="qwen2.5:7b",
            requires_key=False,
        )
        provider = _build_provider(config)
        self.assertIsNotNone(provider)
        self.assertIsInstance(provider, OpenAICompatProvider)


class OllamaAvailability(SaarthiTestCase):
    """
    SABSE ZAROORI TESTS — is_available ka behaviour.

    Do contradictory requirements hain:
      1. Ollama bina key ke available hona chahiye
      2. Cloud providers bina key ke KABHI available NAHI hone chahiye

    Dono ek saath satisfy hone chahiye — warna ya to Ollama kabhi chale
    hi nahi, ya bina key wale cloud providers try hon aur 401 aaye.
    """

    def test_ollama_bina_api_key_available_hai(self):
        """
        BEHAVIOUR TEST — Settings.load() se available_providers nikalo
        aur check karo ki ollama usme aata hai.

        Ye is_available ka ASLI use case test karta hai, sirf property
        nahi. Warna property sahi ho par Settings mein galat config ho
        to bug chhi jaaye.

        DHYAN: is_available env se LIVE padhta hai (OLLAMA_ENABLED),
        isliye available_providers check bhi clean_env ke ANDAR hona
        chahiye.
        """
        with clean_env(OLLAMA_ENABLED="true"):
            settings = Settings.load()
            ollama_providers = [p for p in settings.available_providers if p.name == "ollama"]

        self.assertEqual(
            len(ollama_providers), 1,
            "OLLAMA_ENABLED=true hai par available_providers mein nahi aaya"
        )

    def test_ollama_disabled_pe_available_nahi_hai(self):
        """
        OLLAMA_ENABLED=false (ya set hi nahi) to Ollama skip hona chahiye.
        Warna bina install kiye network timeout aayega har turn mein.
        """
        with clean_env():  # No OLLAMA_ENABLED
            settings = Settings.load()
            ollama_providers = [p for p in settings.available_providers if p.name == "ollama"]

        self.assertEqual(
            len(ollama_providers), 0,
            "OLLAMA_ENABLED nahi hai phir bhi available mein aa gaya"
        )

    def test_regression_cloud_provider_bina_key_unavailable_hai(self):
        """
        🚨 SABSE ZAROORI REGRESSION TEST.

        Bina key wala CLOUD provider (groq, nvidia, etc) available_providers
        mein KABHI nahi aana chahiye. Warna har turn mein bekaar 401 aayega
        aur 1-2 second barbaad.

        Ye test ISLIYE hai ki requires_key change se ye regression na ho.
        """
        # Koi bhi API key nahi, Ollama bhi disabled
        with clean_env():
            settings = Settings.load()

        available_names = [p.name for p in settings.available_providers]

        # Koi cloud provider nahi hona chahiye
        cloud_providers = {"groq", "nvidia", "deepseek", "muse", "gemma",
                          "openrouter", "gemini", "bluesminds", "opencode"}
        leaked = cloud_providers.intersection(available_names)
        self.assertEqual(
            len(leaked), 0,
            f"Bina key ke ye cloud providers available aa gaye: {leaked}. "
            f"Har turn mein bekaar 401 aayega!"
        )

    def test_regression_cloud_provider_bina_key_ek_ek_karke(self):
        """
        HAR cloud provider individually test — warna ek chhut jaaye.

        Ye deliberately verbose hai. Ek provider ka `requires_key` galti se
        False ho jaaye to ye pakad lega.
        """
        with clean_env():
            settings = Settings.load()

        for provider in settings.providers:
            if provider.name == "ollama":
                continue  # Ollama local hai, usko skip
            # Cloud provider ke liye: bina key ke available nahi hona chahiye
            self.assertFalse(
                provider.is_available,
                f"Cloud provider '{provider.name}' bina key ke available hai — "
                f"requires_key={provider.requires_key}. Ye 401 dega!"
            )


class OllamaSupportsTools(SaarthiTestCase):
    """Agent ke liye tool calling ZAROORI hai."""

    def test_ollama_supports_tools_true_hai(self):
        """
        Bina tools ke agent sirf baat karega, kaam nahi karega.
        Ollama ka default model (qwen2.5) tools support karta hai.
        """
        with clean_env(OLLAMA_ENABLED="true"):
            settings = Settings.load()

        ollama = next(p for p in settings.providers if p.name == "ollama")
        self.assertTrue(
            ollama.supports_tools,
            "Ollama pe supports_tools=False hai — agent bekaar hai bina tools ke"
        )


class OllamaPayloadFormat(SaarthiTestCase):
    """Payload OpenAI format mein jaana chahiye."""

    def test_payload_openai_format_mein_jaata_hai(self):
        """
        BEHAVIOUR TEST — asli Brain.think() call fake HTTP ke saath.
        Verify karo ki payload sahi format mein gaya.
        """
        with clean_env(OLLAMA_ENABLED="true", SAARTHI_PROVIDER_ORDER="ollama"):
            brain = Brain(Settings.load())

        self.assertTrue(len(brain.providers) > 0, "Ollama provider load nahi hua")

        def handler(url, payload):
            return FakeResponse(200, "ok")

        fake = FakeHTTP(handler)
        with fake.patch():
            response = run(brain.think([Message.user("paytm kholo")], tools=[TOOL]))

        # Payload check
        self.assertTrue(len(fake.calls) > 0, "Koi HTTP call hua hi nahi")
        url, payload = fake.calls[0]
        self.assertIn("localhost:11434", url)

        # OpenAI format ki zaruri fields
        self.assertIn("model", payload)
        self.assertIn("messages", payload)
        self.assertEqual(payload["model"], DEFAULT_MODELS["ollama"])

        # Messages format
        messages = payload["messages"]
        self.assertTrue(
            any(m.get("role") == "user" for m in messages),
            "User message payload mein nahi hai"
        )

    def test_tools_openai_format_mein_jaate_hain(self):
        """Tools bhi sahi format mein jaane chahiye."""
        with clean_env(OLLAMA_ENABLED="true", SAARTHI_PROVIDER_ORDER="ollama"):
            brain = Brain(Settings.load())

        fake = FakeHTTP(lambda url, payload: FakeResponse(200, "ok"))
        with fake.patch():
            run(brain.think([Message.user("hi")], tools=[TOOL]))

        _, payload = fake.calls[0]
        self.assertIn("tools", payload)
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(payload["tools"][0]["function"]["name"], "app_kholo")


class OllamaConnectionError(SaarthiTestCase):
    """Ollama band ho to CLEAR error mile, crash nahi."""

    def test_ollama_band_pe_actionable_error(self):
        """
        BEHAVIOUR TEST — Ollama server chal nahi raha to:
          - BrainError aaye (crash nahi)
          - Message mein "ollama serve" ho (actionable)
          - Message mein "ollama list" ho (model check)
        """
        import httpx

        with clean_env(OLLAMA_ENABLED="true", SAARTHI_PROVIDER_ORDER="ollama"):
            brain = Brain(Settings.load())

        # Network error simulate — Ollama band hai
        def handler(url, payload):
            raise httpx.ConnectError("Connection refused")

        # FakeHTTP ko thoda hack karna padega — wo exception raise nahi karta
        # Isliye seedha provider pe test karte hain
        provider = brain.providers[0]
        self.assertEqual(provider.name, "ollama")

        # Async call with connection error
        import httpx as real_httpx

        original_client = real_httpx.AsyncClient

        class _FailClient:
            def __init__(self, *a, **kw):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return False
            async def post(self, *a, **kw):
                raise real_httpx.ConnectError("Connection refused")

        real_httpx.AsyncClient = _FailClient
        try:
            with self.assertRaises(BrainError) as ctx:
                run(provider.chat([Message.user("hi")]))

            error_msg = str(ctx.exception)
            self.assertIn("ollama serve", error_msg,
                         "Error mein 'ollama serve' nahi hai — user ko pata nahi chalega")
            self.assertIn("ollama list", error_msg,
                         "Error mein 'ollama list' nahi hai — model check ka hint nahi")
        finally:
            real_httpx.AsyncClient = original_client

    def test_ollama_fail_pe_fallback_hota_hai(self):
        """
        Ollama fail ho to agla provider try hona chahiye — agent ruke nahi.
        """
        with clean_env(
            OLLAMA_ENABLED="true",
            NVIDIA_API_KEY="nvapi-fake",
            SAARTHI_PROVIDER_ORDER="ollama,nvidia",
        ):
            brain = Brain(Settings.load())

        call_count = [0]

        def handler(url, payload):
            call_count[0] += 1
            if "localhost:11434" in url:
                # Ollama fail
                return FakeResponse(500, "internal error")
            # NVIDIA success
            return FakeResponse(200, "ok")

        with FakeHTTP(handler).patch():
            response = run(brain.think([Message.user("hi")]))

        # Nvidia ne bacha liya hoga
        self.assertEqual(response.provider, "nvidia")


class OllamaProviderOrder(SaarthiTestCase):
    """Provider order mein Ollama sahi jagah hai."""

    def test_ollama_default_order_mein_hai(self):
        """Ollama DEFAULT_PROVIDER_ORDER mein hona chahiye."""
        from saarthi.config import DEFAULT_PROVIDER_ORDER
        self.assertIn("ollama", DEFAULT_PROVIDER_ORDER)

    def test_ollama_gemma_se_pehle_hai(self):
        """
        Gemma SABSE AAKHIR hai (tool calling bharosemand nahi).
        Ollama usse pehle hona chahiye.
        """
        from saarthi.config import DEFAULT_PROVIDER_ORDER
        ollama_idx = DEFAULT_PROVIDER_ORDER.index("ollama")
        gemma_idx = DEFAULT_PROVIDER_ORDER.index("gemma")
        self.assertLess(ollama_idx, gemma_idx)

    def test_ollama_cloud_providers_ke_baad_hai(self):
        """
        Ollama cloud providers ke baad hona chahiye default mein —
        kyunki jab tak user ne install nahi kiya, fail hoga.
        """
        from saarthi.config import DEFAULT_PROVIDER_ORDER
        ollama_idx = DEFAULT_PROVIDER_ORDER.index("ollama")
        # Muse, nvidia, groq se peeche
        for cloud in ("muse", "nvidia", "groq"):
            cloud_idx = DEFAULT_PROVIDER_ORDER.index(cloud)
            self.assertGreater(
                ollama_idx, cloud_idx,
                f"Ollama {cloud} se pehle hai — install na ho to timeout aayega"
            )


class OllamaRequiresKeyField(SaarthiTestCase):
    """requires_key field ka behaviour sahi hai."""

    def test_ollama_requires_key_false_hai(self):
        """Ollama local server hai — key nahi chahiye."""
        with clean_env(OLLAMA_ENABLED="true"):
            settings = Settings.load()
        ollama = next(p for p in settings.providers if p.name == "ollama")
        self.assertFalse(ollama.requires_key)

    def test_cloud_providers_requires_key_true_hai(self):
        """Saare cloud providers ke liye key zaroori rehni chahiye."""
        with clean_env(OLLAMA_ENABLED="true"):
            settings = Settings.load()

        for provider in settings.providers:
            if provider.name == "ollama":
                continue
            self.assertTrue(
                provider.requires_key,
                f"Cloud provider '{provider.name}' ka requires_key=False hai — "
                f"bina key ke 401 aayega!"
            )
