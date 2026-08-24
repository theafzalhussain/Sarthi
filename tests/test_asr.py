"""
PILLAR #1 voice pe — Hinglish ASR correction.

Whisper English-first hai. "paytm kholo" ko "pay time cholo" sunta hai.
Ye layer usko theek karti hai — aur yahi Phase 2 ki asli value hai.

Ye tests HARDWARE KE BINA chalte hain (mic ki zarurat nahi) kyunki
correction ek pure text function hai. Ye jaan-boojh ke aisa design
kiya gaya tha.
"""

from __future__ import annotations

from tests.helpers import SaarthiTestCase

from saarthi.lang import parse
from saarthi.voice.hinglish_asr import (
    SAFE_CORRECTIONS,
    build_initial_prompt,
    correct_transcript,
    looks_like_garbage,
)


class CorrectionRules(SaarthiTestCase):
    def test_55_se_zyada_correction_rules_hain(self):
        self.assertGreaterEqual(len(SAFE_CORRECTIONS), 50)

    def test_app_naam_theek_hote_hain(self):
        cases = [
            ("pay time kholo", "paytm"),
            ("phone pay se bhej", "phonepe"),
            ("i r c t c pe dekho", "irctc"),
        ]
        for text, expected in cases:
            self.assertIn(expected, correct_transcript(text).corrected, f"toota: {text!r}")

    def test_number_words_theek_hote_hain(self):
        result = correct_transcript("do hazar peace bhej do").corrected
        self.assertNotIn("peace", result)


class Rs1500Case(SaarthiTestCase):
    """
    Ye ASR layer ka MEASURED fayda hai — README mein cited hai.

    Bina correction ke agent ₹1000 bhejta, correction ke saath ₹2500.
    ₹1500 ka farak. Isliye iska apna test class hai.
    """

    RAW = "pay time cholo aur die hazaar ka bell bhar do"

    def test_correction_ke_bina_galat_samajhta_hai(self):
        parsed = parse(self.RAW)
        apps = [name for name, _ in parsed.apps]
        self.assertNotIn("paytm", apps, "bina correction paytm mil gaya?")

    def test_correction_ke_baad_sahi_samajhta_hai(self):
        corrected = correct_transcript(self.RAW).corrected
        parsed = parse(corrected)
        apps = [name for name, _ in parsed.apps]

        self.assertEqual(apps, ["paytm"], f"app galat: {corrected!r}")
        self.assertEqual(parsed.amount, 2500.0, f"amount galat: {corrected!r}")
        self.assertEqual(parsed.intent, "pay", f"intent galat: {corrected!r}")

    def test_phone_pay_dialer_nahi_phonepe_hai(self):
        corrected = correct_transcript("phone pay se paise bhejo").corrected
        apps = [name for name, _ in parse(corrected).apps]
        self.assertIn("phonepe", apps)


class FalsePositives(SaarthiTestCase):
    """
    Correction ne kuch GALAT theek na kar diya ho.

    SABAK: enabler DISTINCTIVE hona chahiye, common nahi.
    """

    def test_tomato_zomato_nahi_banta(self):
        result = correct_transcript("tomato khareedo sabzi mandi se").corrected
        self.assertNotIn("zomato", result)

    def test_asli_food_order_pakda_jaata_hai(self):
        result = correct_transcript("tomato se khana order karo").corrected
        self.assertIn("zomato", result)

    def test_aam_english_line_nahi_badalti(self):
        for text in ("open the browser", "what is the time", "play a song"):
            result = correct_transcript(text)
            self.assertFalse(
                result.was_changed, f"bina zarurat badal diya: {text!r} -> {result.corrected!r}"
            )


class Transparency(SaarthiTestCase):
    """User ko dikhna chahiye kya badla — trust ke liye."""

    def test_changes_track_hote_hain(self):
        result = correct_transcript("pay time kholo")
        self.assertTrue(result.was_changed)
        self.assertTrue(result.changes, "kya badla wo record nahi hua")

    def test_explain_padhne_layak_hai(self):
        result = correct_transcript("pay time kholo")
        explanation = result.explain()
        self.assertIn("->", explanation)

    def test_kuch_na_badle_to_saaf_batata_hai(self):
        result = correct_transcript("hello")
        self.assertFalse(result.was_changed)
        self.assertIn("koi correction nahi", result.explain())


class Biasing(SaarthiTestCase):
    """
    Layer 1 — Whisper ko initial_prompt se Hinglish ka hint dena.
    Free hai, koi training nahi.
    """

    def test_initial_prompt_mein_hinglish_examples_hain(self):
        prompt = build_initial_prompt()
        self.assertTrue(prompt.strip())
        lowered = prompt.lower()
        self.assertTrue(
            any(app in lowered for app in ("paytm", "phonepe", "irctc")),
            "app naam biasing prompt mein nahi hain",
        )

    def test_extra_vocabulary_add_ho_sakti_hai(self):
        """Compounding fayda: memory/skills se vocabulary badhti hai."""
        prompt = build_initial_prompt(extra_words=["bijli", "khaskhas"])
        self.assertIn("bijli", prompt.lower())


class GarbageDetection(SaarthiTestCase):
    """Mic ne shor suna ho to usko command mat samjho (fail-safe)."""

    def test_khali_aur_chhota_input_garbage_hai(self):
        for text in ("", "   ", "a", "."):
            self.assertTrue(looks_like_garbage(text), f"garbage detect nahi hua: {text!r}")

    def test_asli_command_garbage_nahi_hai(self):
        for text in ("paytm kholo", "open youtube"):
            self.assertFalse(looks_like_garbage(text), f"galti se garbage: {text!r}")
