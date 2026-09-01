"""
PILLAR #1 — Hinglish samajhna.

Ye project ki JAAN hai. Yahan kuch toota to pura differentiator gaya.
Isliye ye tests sabse detail mein hain.
"""

from __future__ import annotations

from tests.helpers import SaarthiTestCase

from saarthi.lang import build_system_prompt, build_user_message, detect_language, parse
from saarthi.lang.lexicon import INDIAN_APPS, VERB_INTENTS
from saarthi.lang.normalize import (
    extract_amount,
    has_devanagari,
    parse_hindi_number,
    transliterate,
)


class IndianApps(SaarthiTestCase):
    """PILLAR #4 — Indian apps ka database."""

    def test_110_apps_hain(self):
        self.assertEqual(len(INDIAN_APPS), 110)

    def test_zaroori_indian_apps_maujood_hain(self):
        must_have = [
            "paytm", "phonepe", "irctc", "zomato", "swiggy", "flipkart",
            "myntra", "ola", "hotstar", "jio", "cred", "zerodha",
            "whatsapp", "youtube", "instagram", "gmail",
        ]
        for app in must_have:
            self.assertIn(app, INDIAN_APPS, f"'{app}' database se gayab hai")

    def test_har_app_ka_package_naam_hai(self):
        for app, package in INDIAN_APPS.items():
            self.assertTrue(package.strip(), f"'{app}' ka package naam khali hai")
            self.assertIn(".", package, f"'{app}' ka package galat lagta hai: {package}")

    def test_app_naam_lowercase_hain(self):
        for app in INDIAN_APPS:
            self.assertEqual(app, app.lower(), f"'{app}' lowercase nahi hai")


class IntentParsing(SaarthiTestCase):
    """Hinglish verb -> intent."""

    def test_aam_intents_pakde_jaate_hain(self):
        cases = [
            ("paytm kholo", "open"),
            ("youtube khol de", "open"),
            ("screenshot lo", "screenshot"),
        ]
        for text, expected in cases:
            self.assertEqual(parse(text).intent, expected, f"toota: {text!r}")

    def test_18_intents_define_hain(self):
        self.assertGreaterEqual(len(VERB_INTENTS), 18)

    def test_risky_keywords_flag_lagate_hain(self):
        for text in ("paise bhej do", "payment karna hai", "delete kar do"):
            self.assertTrue(parse(text).risky, f"risky flag nahi laga: {text!r}")

    def test_aam_baat_risky_nahi_hai(self):
        for text in ("mausam kaisa hai", "time kya hua", "screenshot lo"):
            self.assertFalse(parse(text).risky, f"galti se risky: {text!r}")


class HindiNumbers(SaarthiTestCase):
    """
    Hindi ke numbers — sau/hazaar/lakh/crore + dhai/saadhe/paune.

    Ye important hai kyunki galat amount = galat paisa.
    """

    def test_simple_numbers(self):
        cases = [("sau", 100.0), ("do hazaar", 2000.0), ("teen sau", 300.0),
                 ("paanch lakh", 500000.0), ("ek crore", 10000000.0)]
        for text, expected in cases:
            self.assertEqual(parse_hindi_number(text), expected, f"toota: {text!r}")

    def test_fraction_words(self):
        cases = [("dhai hazaar", 2500.0), ("saadhe teen sau", 350.0),
                 ("paune do lakh", 175000.0), ("saadhe char hazaar", 4500.0)]
        for text, expected in cases:
            self.assertEqual(parse_hindi_number(text), expected, f"toota: {text!r}")

    def test_digit_wale_amount(self):
        cases = [("2000 rupay bhej do", 2000.0), ("₹1500 ka bill", 1500.0),
                 ("rs 500 transfer", 500.0), ("rs. 2,500 ka recharge", 2500.0)]
        for text, expected in cases:
            self.assertEqual(extract_amount(text), expected, f"toota: {text!r}")


class Devanagari(SaarthiTestCase):
    """Devanagari -> roman (kyunki hamara lexicon roman mein hai)."""

    def test_devanagari_detect_hota_hai(self):
        self.assertTrue(has_devanagari("पेटीएम खोलो"))
        self.assertFalse(has_devanagari("paytm kholo"))

    def test_devanagari_roman_mein_badalta_hai(self):
        result = transliterate("पेटीएम")
        self.assertFalse(has_devanagari(result), "Devanagari bacha hua hai")

    def test_parse_devanagari_flag_lagata_hai(self):
        self.assertTrue(parse("पेटीएम खोलो").had_devanagari)
        self.assertFalse(parse("paytm kholo").had_devanagari)


class LanguageDetection(SaarthiTestCase):
    """
    User ki bhasha detect karna — interface English hai par jawab
    user ki bhasha mein aata hai.
    """

    def test_english_detect_hota_hai(self):
        for text in (
            "open youtube and play a song",
            "hello how are you",
            "what is the weather today",
            "remember my mom number is 98765",
            "can you open my browser and search for flights",
            "how much disk space is left",
        ):
            self.assertEqual(detect_language(text), "english", f"toota: {text!r}")

    def test_hinglish_detect_hota_hai(self):
        for text in (
            "youtube pe gaana chala do",
            "bhai ek song play kar dena",
            "mere phone me kya notifications hain",
            "laptop pe disk space batao",
            "yaad rakh ki mummy ka number 98765 hai",
        ):
            self.assertEqual(detect_language(text), "hinglish", f"toota: {text!r}")

    def test_devanagari_hinglish_hai(self):
        self.assertEqual(detect_language("पेटीएम खोलो"), "hinglish")

    def test_khali_input_pe_hinglish_default(self):
        # Fail-safe: doubt ho to Hinglish (Pillar #1)
        for text in ("", "   ", "123", "!!!"):
            self.assertEqual(detect_language(text), "hinglish")

    def test_lambi_english_line_ek_marker_se_hinglish_nahi_banti(self):
        # Ek ittefaqi marker lambi English line ko Hinglish na bana de
        text = "please open the browser and search for the best hotel deals de"
        self.assertEqual(detect_language(text), "english")


class PromptBuilding(SaarthiTestCase):
    """System prompt aur per-turn hints."""

    def test_default_language_rule_auto_hai(self):
        prompt = build_system_prompt()
        self.assertIn("MIRROR THE USER", prompt)

    def test_fixed_language_set_kar_sakte_hain(self):
        english = build_system_prompt(language="english")
        self.assertNotIn("MIRROR THE USER", english)

    def test_per_turn_language_hint_jaata_hai(self):
        english = build_user_message(parse("play a song"), "english")
        self.assertIn("reply in English", english)

        hinglish = build_user_message(parse("gaana chala do"), "hinglish")
        self.assertIn("Hinglish mein jawab de", hinglish)

    def test_bina_hint_ke_kuch_extra_nahi_jaata(self):
        self.assertNotIn("language:", build_user_message(parse("hi")))

    def test_structured_hint_llm_ko_jaata_hai(self):
        # Yahi SAARTHI ka differentiator hai — pre-analyzed hints
        message = build_user_message(parse("paytm se dhai hazaar bhej do"))
        self.assertIn("paytm", message.lower())

    def test_zaroori_rules_prompt_mein_hain(self):
        prompt = build_system_prompt()
        must_have = [
            "KAAM POORA KAR",           # aadha kaam mat chhodo
            "MAIN NAHI KAR SAKTA",      # anti-refusal (rule #0)
            "KAI KAAM EK LINE MEIN",    # multi-task
            "FAIL HO TO",               # retry / haar mat maan
            "CHALU KAAM MAT TODO",      # tab safety
            "dobara mat puch",          # jo bata diya wo mat pucho
            "xdg-open",                  # OS awareness / shell rule
        ]
        for rule in must_have:
            self.assertIn(rule, prompt, f"Rule gayab: {rule}")

    def test_safety_rules_prompt_mein_bachi_hui_hain(self):
        prompt = build_system_prompt()
        self.assertIn("final payment button", prompt)
        self.assertIn("OTP", prompt)
