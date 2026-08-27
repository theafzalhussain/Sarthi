"""
Brain — 8 providers, fallback, aur provider health.

Ye tests ASLI NETWORK CALL NAHI karte. httpx fake ho jaata hai.
Isliye:
  - koi API key nahi chahiye
  - rate limit nahi lagti
  - internet ke bina bhi chalte hain
"""

from __future__ import annotations

import asyncio

from tests.helpers import FakeHTTP, FakeResponse, SaarthiTestCase, clean_env

from saarthi.brain import Brain
from saarthi.brain.types import (
    BrainError,
    Message,
    ModelUnavailableError,
    RateLimitError,
    ToolSchema,
    classify_http_error,
)
from saarthi.config import Settings


def run(coro):
    """Chhota helper — har test mein event loop banane se bachne ke liye."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def ok_response(url, payload):
    return FakeResponse(200, "ok")


TOOL = ToolSchema(
    name="app_kholo",
    description="app kholo",
    parameters={"type": "object", "properties": {}},
)


class ErrorClassification(SaarthiTestCase):
    """
    HTTP error ko sahi samajhna.

    Ye farak karna zaroori hai:
      PERMANENT (model hi kharab)  -> provider session bhar hatao
      TEMPORARY (limit / server)   -> thodi der cooldown, phir wapas

    Warna dead provider har message pe try hota rehta hai aur user
    ko har baar 1-2 second extra intezaar karna padta hai.
    """

    # Ye asli response body hai jo Bluesminds ne di thi
    GLM_PRICING_ERROR = (
        '{"error":{"message":"模型 glm-5.2 的价格尚未由管理员配置，暂时无法使用；'
        'Model glm-5.2 has not been priced by the administrator yet. Please '
        'contact the site administrator to enable this model.",'
        '"type":"new_api_error","code":"model_price_error"}}'
    )

    def test_400_model_pricing_error_permanent_hai(self):
        error = classify_http_error("bluesminds", 400, self.GLM_PRICING_ERROR)
        self.assertIsInstance(error, ModelUnavailableError)

    def test_pricing_error_actionable_hai(self):
        message = str(classify_http_error("bluesminds", 400, self.GLM_PRICING_ERROR))
        self.assertIn("/models", message)
        self.assertIn("BLUESMINDS_MODEL", message)

    def test_404_permanent_hai(self):
        self.assertIsInstance(
            classify_http_error("groq", 404, "model_not_found"), ModelUnavailableError
        )

    def test_401_403_permanent_hai(self):
        for status in (401, 403):
            self.assertIsInstance(
                classify_http_error("groq", status, "bad key"), ModelUnavailableError
            )

    def test_429_temporary_hai(self):
        self.assertIsInstance(
            classify_http_error("groq", 429, "rate limit"), RateLimitError
        )

    def test_5xx_temporary_hai(self):
        """NVIDIA ne 500 diya tha — wo unka server issue hai, temporary."""
        for status in (500, 502, 503, 504):
            self.assertIsInstance(
                classify_http_error("nvidia", status, "Internal server error"),
                RateLimitError,
                f"HTTP {status} temporary nahi maana gaya",
            )

    def test_aam_400_permanent_nahi_hai(self):
        error = classify_http_error("groq", 400, "bad request: temperature invalid")
        self.assertIs(type(error), BrainError)


class ProviderHealth(SaarthiTestCase):
    """Dead provider dobara try nahi hona chahiye — waqt bachta hai."""

    def build_brain(self):
        with clean_env(
            BLUESMINDS_API_KEY="fake",
            NVIDIA_API_KEY="nvapi-fake",
            SAARTHI_PROVIDER_ORDER="bluesminds,deepseek",
        ):
            return Brain(Settings.load())

    def test_permanent_fail_pe_provider_session_bhar_hat_jaata_hai(self):
        brain = self.build_brain()
        self.assertEqual(brain.providers[0].name, "bluesminds")

        def handler(url, payload):
            if "bluesminds" in url:
                return FakeResponse(400, ErrorClassification.GLM_PRICING_ERROR)
            return FakeResponse(200, "ok")

        fake = FakeHTTP(handler)
        with fake.patch():
            # Turn 1 — bluesminds try hua, fail, deepseek ne bacha liya
            first = run(brain.think([Message.user("hi")]))
            self.assertEqual(first.provider, "deepseek")
            self.assertIn("bluesminds", fake.provider_hits())

            # Turn 2 — bluesminds DOBARA TRY NAHI hona chahiye
            fake.calls.clear()
            second = run(brain.think([Message.user("phir")]))
            self.assertEqual(second.provider, "deepseek")
            self.assertNotIn(
                "bluesminds",
                fake.provider_hits(),
                "Dead provider dobara try hua — har turn pe waqt barbaad hoga",
            )

        self.assertTrue(brain.health()["bluesminds"].startswith("dead"))

    def test_rate_limit_pe_cooldown_lagta_hai_dead_nahi(self):
        brain = self.build_brain()

        def handler(url, payload):
            if "bluesminds" in url:
                return FakeResponse(429, "rate limit exceeded")
            return FakeResponse(200, "ok")

        with FakeHTTP(handler).patch():
            run(brain.think([Message.user("hi")]))

        state = brain.health()["bluesminds"]
        self.assertTrue(state.startswith("cooldown"), state)
        self.assertFalse(state.startswith("dead"))

    def test_reset_health_sabko_wapas_zinda_karta_hai(self):
        brain = self.build_brain()
        brain.mark_dead("bluesminds", "test")
        brain.reset_health()
        self.assertTrue(all(v == "ok" for v in brain.health().values()))

    def test_saare_dead_ho_jaayein_to_phir_bhi_try_karta_hai(self):
        """Kuch na karne se behtar hai dobara try karna."""
        brain = self.build_brain()
        for provider in brain.providers:
            brain.mark_dead(provider.name, "test")

        with FakeHTTP(ok_response).patch():
            response = run(brain.think([Message.user("hi")]))
        self.assertTrue(response.provider, "sab dead the to koi try hi nahi hua")

    def test_fallback_hone_pe_user_ko_khabar_milti_hai(self):
        brain = self.build_brain()
        notes = []
        brain.notify = lambda kind, text: notes.append(text)

        def handler(url, payload):
            if "bluesminds" in url:
                return FakeResponse(400, ErrorClassification.GLM_PRICING_ERROR)
            return FakeResponse(200, "ok")

        with FakeHTTP(handler).patch():
            run(brain.think([Message.user("hi")]))

        self.assertTrue(
            any("bluesminds" in note for note in notes),
            "Provider hata diya par user ko bataya nahi",
        )


class ToolFiltering(SaarthiTestCase):
    """
    Jo model tools support nahi karta, usko tool wale kaam se peeche
    dhakelna hai.

    Kyun: aise models tools ko CHUP-CHAAP ignore kar dete hain. Phir
    bas text bhejte hain, agent ka loop khatam, aur user sochta hai
    "kaam kyun nahi hua". Silent failure sabse buri cheez hai.
    """

    def build_brain(self, order):
        with clean_env(NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER=order):
            return Brain(Settings.load())

    def test_tools_maange_to_gemma_skip_hota_hai(self):
        # gemma JAAN-BOOJH KE pehle rakha hai
        brain = self.build_brain("gemma,deepseek")
        self.assertEqual(brain.providers[0].name, "gemma")

        with FakeHTTP(ok_response).patch():
            response = run(brain.think([Message.user("paytm kholo")], tools=[TOOL]))

        self.assertEqual(
            response.provider,
            "deepseek",
            "gemma tools support nahi karta par usko tool call bhej diya",
        )

    def test_tools_na_maange_to_gemma_chalta_hai(self):
        brain = self.build_brain("gemma,deepseek")
        with FakeHTTP(ok_response).patch():
            response = run(brain.think([Message.user("hi")]))
        self.assertEqual(response.provider, "gemma")

    def test_has_tools_aur_has_vision_sahi_batate_hain(self):
        brain = self.build_brain("deepseek,muse,gemma")
        self.assertTrue(brain.has_tools)
        self.assertTrue(brain.has_vision)


class VisionRouting(SaarthiTestCase):
    """Screenshot sirf aankh wale model ko jaana chahiye."""

    def test_image_wala_message_vision_model_ko_jaata_hai(self):
        with clean_env(
            NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="deepseek,muse,gemma"
        ):
            brain = Brain(Settings.load())

        message = Message.user("ye screen dekh", image_b64="ZmFrZQ==")
        with FakeHTTP(ok_response).patch():
            response = run(brain.think([message]))

        self.assertIn(
            response.provider,
            ("muse", "gemma"),
            f"image text-only model ko chala gaya: {response.provider}",
        )

    def test_muse_ko_priority_milti_hai(self):
        """Muse vision + tools DONO karta hai — Gemini se ek step bachta hai."""
        with clean_env(
            NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="deepseek,muse,gemma"
        ):
            brain = Brain(Settings.load())

        message = Message.user("dekh", image_b64="ZmFrZQ==")
        with FakeHTTP(ok_response).patch():
            response = run(brain.think([message]))
        self.assertEqual(response.provider, "muse")

    def test_image_payload_openai_format_mein_jaata_hai(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="muse"):
            brain = Brain(Settings.load())

        fake = FakeHTTP(ok_response)
        with fake.patch():
            run(brain.think([Message.user("dekh", image_b64="ZmFrZQ==")]))

        messages = fake.calls[0][1]["messages"]
        self.assertTrue(
            any(isinstance(m.get("content"), list) for m in messages),
            "image content list format mein nahi gaya",
        )


class ReasoningModels(SaarthiTestCase):
    """DeepSeek/Muse jaise reasoning models ke do khaas issue."""

    def test_deepseek_ka_thinking_off_jaata_hai(self):
        """
        Warna pura chain-of-thought reply mein aa jaata hai — free tier
        pe tokens barbaad, aur user ko model ki bakbak dikhti hai.
        """
        with clean_env(NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="deepseek"):
            brain = Brain(Settings.load())

        fake = FakeHTTP(ok_response)
        with fake.patch():
            run(brain.think([Message.user("hi")]))

        payload = fake.calls[0][1]
        self.assertEqual(payload.get("chat_template_kwargs"), {"thinking": False})

        # Model naam DEFAULT_MODELS se lete hain, hardcode NAHI.
        #
        # Pehle yahan "deepseek-ai/deepseek-v4-pro" likha tha. Wo model
        # 2026-08-07 pe EOL ho gaya, config mein "-0813" version aa gaya,
        # aur ye test fail hone laga — jabki code SAHI tha. Test ka kaam
        # yahan `thinking: False` verify karna hai, model version nahi.
        from saarthi.config import DEFAULT_MODELS

        self.assertEqual(payload["model"], DEFAULT_MODELS["deepseek"])

    def test_muse_pe_extra_field_nahi_jaata(self):
        with clean_env(NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="muse"):
            brain = Brain(Settings.load())

        fake = FakeHTTP(ok_response)
        with fake.patch():
            run(brain.think([Message.user("hi")]))
        self.assertNotIn("chat_template_kwargs", fake.calls[0][1])

    def test_khali_content_pe_reasoning_field_use_hota_hai(self):
        """
        Reasoning model kabhi content KHALI bhejta hai aur asli jawab
        reasoning_content mein hota hai. Pehle user ko "(kuch jawab nahi
        aaya)" dikhta tha jabki model ne jawab diya tha.
        """
        with clean_env(NVIDIA_API_KEY="nvapi-fake", SAARTHI_PROVIDER_ORDER="deepseek"):
            brain = Brain(Settings.load())

        def handler(url, payload):
            return FakeResponse(
                200,
                "ok",
                payload={
                    "choices": [
                        {"message": {"content": "", "reasoning_content": "jawab yahan hai"}}
                    ],
                    "usage": {},
                },
            )

        with FakeHTTP(handler).patch():
            response = run(brain.think([Message.user("hi")]))

        self.assertEqual(response.text, "jawab yahan hai")



class GenerationSettingsInPayload(SaarthiTestCase):
    """
    BUG#11 ka doosra hissa — settings config mein pahunchna KAAFI NAHI,
    unhe PAYLOAD mein bhi jaana chahiye.

    Config test pass ho jaaye par payload mein na jaaye, to bug zinda
    rehta hai. Isliye ye tests asli HTTP payload check karte hain.
    """

    def payload_for(self, **env):
        env.setdefault("NVIDIA_API_KEY", "nvapi-fake")
        with clean_env(**env):
            brain = Brain(Settings.load())

        fake = FakeHTTP(ok_response)
        with fake.patch():
            run(brain.think([Message.user("hi")]))
        return fake.calls[0][1]

    def test_max_tokens_payload_mein_jaata_hai(self):
        payload = self.payload_for(
            SAARTHI_PROVIDER_ORDER="nvidia", NVIDIA_MAX_TOKENS="16384"
        )
        self.assertEqual(payload["max_tokens"], 16384)

    def test_top_p_payload_mein_jaata_hai(self):
        payload = self.payload_for(
            SAARTHI_PROVIDER_ORDER="nvidia", NVIDIA_TOP_P="0.95"
        )
        self.assertEqual(payload["top_p"], 0.95)

    def test_top_p_set_na_ho_to_payload_mein_nahi_jaata(self):
        """Provider ka apna default chalne do."""
        payload = self.payload_for(SAARTHI_PROVIDER_ORDER="nvidia")
        self.assertNotIn("top_p", payload)

    def test_enable_thinking_payload_mein_jaata_hai(self):
        payload = self.payload_for(
            SAARTHI_PROVIDER_ORDER="nvidia", NVIDIA_ENABLE_THINKING="true"
        )
        self.assertEqual(payload.get("chat_template_kwargs"), {"thinking": True})

    def test_global_max_tokens_default_ban_jaata_hai(self):
        payload = self.payload_for(
            SAARTHI_PROVIDER_ORDER="muse", SAARTHI_MAX_TOKENS="8192"
        )
        self.assertEqual(payload["max_tokens"], 8192)

    def test_per_provider_global_ko_override_karta_hai(self):
        payload = self.payload_for(
            SAARTHI_PROVIDER_ORDER="nvidia",
            SAARTHI_MAX_TOKENS="8192",
            NVIDIA_MAX_TOKENS="16384",
        )
        self.assertEqual(payload["max_tokens"], 16384, "per-provider jeetna chahiye")

    def test_purana_2048_hardcode_nahi_bacha(self):
        """
        Reasoning model ke saath 2048 bahut kam hai — jawab beech mein
        kat jaata tha.
        """
        payload = self.payload_for(SAARTHI_PROVIDER_ORDER="deepseek")
        self.assertGreaterEqual(payload["max_tokens"], 4096)
