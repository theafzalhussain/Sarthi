"""
PHASE 5A — Human voice upgrade ke tests.

Sab PURE LOGIC hain — mic, speaker, internet ki zarurat nahi. Ye
repo ka design rule hai: audio I/O alag, logic alag.

Covered:
    - Hindi numbers (Indian system)
    - digits -> Hindi words (time, decimal, plain)
    - Roman -> Devanagari transliteration (dict + conservative rules)
    - Script detection / voice choice (hinglish vs english)
    - Sentence splitting + SentenceBuffer (streaming TTS ka dil)
    - Barge-in detector (pure state machine)
    - TTS voice auto-selection
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from tests.helpers import SaarthiTestCase

from saarthi.voice.hinglish_tts import (
    HINDI_WORDS,
    SentenceBuffer,
    detect_script,
    digits_to_hindi_words,
    looks_like_hinglish,
    number_to_hindi,
    pick_voice_kind,
    prepare_hinglish_speech,
    roman_to_devanagari,
    split_into_sentences,
    transliterate_word,
)
from saarthi.voice.tts import TTSConfig, TTSEngine


# ======================================================================
#  Hindi numbers
# ======================================================================


class HindiNumbers(SaarthiTestCase):
    def test_basic_numbers(self):
        cases = {
            0: "shunya",
            1: "ek",
            9: "nau",
            10: "das",
            15: "pandrah",
            20: "bees",
            21: "ekkais",
            50: "pachaas",
            99: "ninyaanve",
            100: "ek sau",
        }
        for n, expected in cases.items():
            self.assertEqual(number_to_hindi(n), expected, f"toota: {n}")

    def test_bill_style_numbers(self):
        # Ye asli user commands wale numbers hain
        self.assertEqual(number_to_hindi(2500), "do hazaar paanch sau")
        self.assertEqual(number_to_hindi(350), "teen sau pachaas")
        self.assertEqual(number_to_hindi(45000), "paintaalees hazaar")

    def test_indian_system(self):
        # lakh/crore — Indian grouping (100000 = 1 lakh, NOT "hundred thousand")
        self.assertIn("lakh", number_to_hindi(150000))
        self.assertIn("crore", number_to_hindi(25000000))
        self.assertTrue(number_to_hindi(100000).startswith("ek lakh"))

    def test_negative_and_small(self):
        self.assertTrue(number_to_hindi(-5).startswith("minus"))
        self.assertEqual(number_to_hindi(7), "saat")


class DigitsToWords(SaarthiTestCase):
    def test_plain_number(self):
        self.assertIn("do hazaar paanch sau", digits_to_hindi_words("2500 ka bill"))

    def test_time_pattern(self):
        result = digits_to_hindi_words("8:30 baje milte hain")
        self.assertIn("aath", result)
        self.assertIn("bajke", result)

    def test_non_number_untouched(self):
        self.assertEqual(digits_to_hindi_words("bhai chai de"), "bhai chai de")


# ======================================================================
#  Roman -> Devanagari
# ======================================================================


class Transliteration(SaarthiTestCase):
    def test_common_words_dict_se(self):
        # Dict entries — ye pakka Devanagari aane chahiye
        for word in ("bhai", "kholo", "chai", "mujhe", "chahiye", "aur"):
            self.assertEqual(
                transliterate_word(word),
                HINDI_WORDS[word],
                f"dict word fail: {word}",
            )

    def test_brands_latin_rehte_hain(self):
        # Brand/tech names Hindi voice bhi Latin theek padhti hai
        for brand in ("paytm", "youtube", "whatsapp"):
            self.assertEqual(transliterate_word(brand), brand)

    def test_sentence_structure(self):
        result = roman_to_devanagari("bhai paytm kholo")
        self.assertIn("भाई", result)
        self.assertIn("खोलो", result)
        self.assertIn("paytm", result)  # brand preserved

    def test_real_command(self):
        # ASLI command — SAARTHI ka signature use-case
        result = prepare_hinglish_speech("mummy ko 350 bhej do aur mujhe batana")
        self.assertIn("मम्मी", result)
        self.assertIn("को", result)
        self.assertIn("तीन सौ", result)
        self.assertIn("भेज", result)
        # Koi roman Hinglish word reh nahi jaana chahiye jo dict mein tha
        self.assertNotIn("mummy", result)

    def test_punctuation_bachta_hai(self):
        result = transliterate_word("kholo!")
        self.assertTrue(result.endswith("!"))
        self.assertIn("खोलो", result)

    def test_numbers_pehle_words_bane(self):
        # 2500 pehle "do hazaar paanch sau" hona chahiye, phir Devanagari
        result = prepare_hinglish_speech("2500 rupay")
        self.assertIn("दो", result)
        self.assertIn("हज़ार", result)
        self.assertNotIn("2500", result)

    def test_unknown_word_latin_reh_sakta_hai(self):
        # Conservative rule: jo pakka nahi, wo Latin hi rehta hai
        # (galat Devanagari se accha)
        weird = transliterate_word("xyzzy")
        self.assertIsInstance(weird, str)  # crash nahi — bas


class ScriptDetection(SaarthiTestCase):
    def test_devanagari_detect(self):
        self.assertEqual(detect_script("नमस्ते भाई"), "devanagari")

    def test_latin_detect(self):
        self.assertEqual(detect_script("bhai kholo"), "latin")

    def test_hinglish_vs_english(self):
        self.assertTrue(looks_like_hinglish("bhai paytm kholo"))
        self.assertFalse(looks_like_hinglish("what is the weather today"))

    def test_voice_choice(self):
        self.assertEqual(pick_voice_kind("bhai paytm kholo"), "hi")
        self.assertEqual(pick_voice_kind("what is the weather today"), "en")
        self.assertEqual(pick_voice_kind("नमस्ते"), "hi")


# ======================================================================
#  Streaming TTS — sentence splitting + buffer
# ======================================================================


class SentenceSplitting(SaarthiTestCase):
    def test_basic_split(self):
        # min_chars=10 — chhote sentences bhi alag rehne do (split test)
        text = "Kaam ho gaya bhai. Ab kya karein? Kuch aur chahiye!"
        result = split_into_sentences(text, min_chars=10)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "Kaam ho gaya bhai.")
        self.assertEqual(result[1], "Ab kya karein?")
        self.assertEqual(result[2], "Kuch aur chahiye!")

    def test_chhote_tukde_merge_hote_hain(self):
        # Default: chhota sentence aage ke saath judta hai — "Ho gaya."
        # akela bolna choppy lagta hai
        result = split_into_sentences("Ho gaya. Ab kya karein? Kuch aur!")
        self.assertEqual(len(result), 1)

    def test_short_text_ek_saath(self):
        self.assertEqual(split_into_sentences("Ho gaya."), ["Ho gaya."])

    def test_comma_split_nahi_karta(self):
        # "bhai, suno" ek sentence hai — comma pe todna galat
        result = split_into_sentences("bhai, suno, ye dekho. Yeh raha", min_chars=10)
        self.assertEqual(len(result), 2)
        self.assertIn("bhai, suno, ye dekho.", result[0])

    def test_lamba_sentence_comma_pe_katta_hai(self):
        text = (
            "Ye bahut lamba sentence hai jisme bahut saari baatein hain, "
            "aur ye aage bhi badhta ja raha hai, aur rukne ka naam nahi "
            "le raha hai bilkul bhi, kya kar sakte hain aise mein?"
        )
        result = split_into_sentences(text, min_chars=10, max_chars=80)
        self.assertGreater(len(result), 1)
        for piece in result:
            self.assertLessEqual(len(piece), 80)

    def test_empty(self):
        self.assertEqual(split_into_sentences(""), [])


class SentenceBufferTest(SaarthiTestCase):
    def test_tokens_se_sentences(self):
        buf = SentenceBuffer(min_chars=10)
        # feed() khud ready sentences return karta hai (gate same hai)
        self.assertEqual(buf.feed("Ho gaya"), [])  # abhi adhoora (7 < 10)
        ready = buf.feed(" bhai. Ab ")
        self.assertEqual(ready, ["Ho gaya bhai."])
        # "Ab " pending hai
        self.assertEqual(buf.pending_len, 3)

    def test_tail_complete_to_pura_nikalta_hai(self):
        buf = SentenceBuffer(min_chars=10)
        ready = buf.feed("Pehla yahan. Doosra yahan?")
        # Dono complete — dono ek saath nikalne chahiye
        self.assertEqual(len(ready), 2)

    def test_comma_pe_trigger_nahi(self):
        buf = SentenceBuffer(min_chars=10)
        ready = buf.feed("bhai, suno, ye dekho. Yeh raha")
        # Sirf strong end (.) pe nikla — commas pe nahi
        self.assertEqual(ready, ["bhai, suno, ye dekho."])
        self.assertEqual(buf.flush(), "Yeh raha")

    def test_flush_bacha_hua_deta_hai(self):
        buf = SentenceBuffer(min_chars=10)
        buf.feed("kuch adhoora")
        self.assertEqual(buf.flush(), "kuch adhoora")
        self.assertEqual(buf.pending_len, 0)

    def test_clear(self):
        buf = SentenceBuffer()
        buf.feed("kuch kuch")
        buf.clear()
        self.assertEqual(buf.flush(), "")


# ======================================================================
#  Barge-in — pure state machine
# ======================================================================


class BargeInDetectorTest(SaarthiTestCase):
    def _detector(self, **kwargs):
        from saarthi.voice.audio import BargeInDetector

        return BargeInDetector(**kwargs)

    def test_chup_rahe_to_trigger_nahi(self):
        det = self._detector()
        # Baseline ke barabar values — kabhi trigger nahi
        for _ in range(50):
            self.assertFalse(det.feed(100.0))
        self.assertFalse(det.triggered)

    def test_calibration_ke_baad_speaker_bhi_trigger_na_kare(self):
        det = self._detector(ratio=2.8, loud_chunks_needed=5, calibrate_chunks=10)
        # Calibration: speaker ki awaaz mic mein (baseline ~800)
        for _ in range(10):
            det.feed(800.0)
        # Speaker aise hi bolta rahega — trigger nahi hona chahiye
        for _ in range(30):
            self.assertFalse(det.feed(850.0))

    def test_user_zor_se_bole_to_trigger(self):
        det = self._detector(ratio=2.8, loud_chunks_needed=5, calibrate_chunks=10)
        for _ in range(10):
            det.feed(800.0)  # speaker baseline
        # User bol raha hai — baseline se ~4x
        for _ in range(4):
            self.assertFalse(det.feed(3500.0))
        # 5th loud chunk pe trigger
        self.assertTrue(det.feed(3500.0))

    def test_ek_spike_trigger_na_kare(self):
        det = self._detector(ratio=2.8, loud_chunks_needed=5, calibrate_chunks=10)
        for _ in range(10):
            det.feed(800.0)
        # Hichki — ek loud chunk, phir shant
        det.feed(3500.0)
        for _ in range(10):
            det.feed(850.0)
        self.assertFalse(det.triggered)

    def test_reset(self):
        det = self._detector()
        for _ in range(10):
            det.feed(800.0)
        det.feed(9999.0)
        det.reset()
        self.assertFalse(det.triggered)
        self.assertTrue(det.calibrating)  # dobara calibrate karega


# ======================================================================
#  TTS voice auto-selection (network nahi — sirf config logic)
# ======================================================================


class TTSAutoVoice(SaarthiTestCase):
    def _edge(self, **overrides):
        from saarthi.voice.tts import EdgeTTS

        config = TTSConfig(**overrides)
        return EdgeTTS(config)

    def test_auto_hinglish_pe_hindi_voice(self):
        edge = self._edge()
        self.assertEqual(edge._resolve_voice("bhai chai lao"), "hi-IN-MadhurNeural")

    def test_auto_english_pe_ryan(self):
        edge = self._edge()
        self.assertEqual(
            edge._resolve_voice("Hello there, how are you doing today"),
            "en-GB-RyanNeural",
        )

    def test_fixed_voice_override(self):
        edge = self._edge(edge_voice="en-IN-PrabhatNeural")
        self.assertEqual(edge._resolve_voice("kuch bhi"), "en-IN-PrabhatNeural")

    def test_config_defaults(self):
        cfg = TTSConfig()
        self.assertEqual(cfg.edge_voice, "auto")
        self.assertTrue(cfg.hinglish_devanagari)

    def test_env_overrides(self):
        env = {
            "EDGE_VOICE": "hi-IN-SwaraNeural",
            "EDGE_HINGLISH_VOICE": "hi-IN-MadhurNeural",
            "TTS_DEVANAGARI": "false",
            "TTS_BACKEND": "auto",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            # dotenv-loaded values ignore karne ke liye fresh from_env
            cfg = TTSConfig.from_env()
        self.assertEqual(cfg.edge_voice, "hi-IN-SwaraNeural")
        self.assertFalse(cfg.hinglish_devanagari)

    def test_engine_hindi_pipeline_flag(self):
        # Engine ka _voice_will_be_hindi — backend 'null' pe bhi text
        # ke hisaab se sahi jawab de
        engine = TTSEngine(TTSConfig(backend="null"))
        self.assertTrue(engine._voice_will_be_hindi("bhai chai lao"))
        self.assertFalse(engine._voice_will_be_hindi("Please check the file"))


# ======================================================================
#  Wake config — naya oww mode
# ======================================================================


class OpenWakeWordConfig(SaarthiTestCase):
    def test_oww_mode_registered(self):
        from saarthi.voice.wake import WAKE_MODES, OpenWakeWordWake

        for alias in ("oww", "openwakeword", "free"):
            self.assertIn(alias, WAKE_MODES)
            self.assertEqual(WAKE_MODES[alias], OpenWakeWordWake)

    def test_oww_threshold_from_env(self):
        from saarthi.voice.wake import WakeConfig

        with mock.patch.dict(os.environ, {"OWW_THRESHOLD": "0.7"}, clear=False):
            cfg = WakeConfig.from_env()
        self.assertAlmostEqual(cfg.oww_threshold, 0.7)

    def test_oww_default_threshold(self):
        from saarthi.voice.wake import WakeConfig

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWW_THRESHOLD", None)
            cfg = WakeConfig.from_env()
        self.assertAlmostEqual(cfg.oww_threshold, 0.5)

    def test_fallback_jab_mic_nahi(self):
        # Hardware ke bina detector push-to-talk pe fallback karta hai —
        # agent KABHI nahi rukta (repo ka fail-safe rule)
        from saarthi.voice.wake import WakeConfig, create_wake_detector

        detector = create_wake_detector(WakeConfig(mode="oww"))
        # Sandbox mein mic nahi — fallback hoga ya oww khud; dono theek.
        # Zaroori: koi crash nahi + detector mila
        self.assertIsNotNone(detector)


if __name__ == "__main__":
    unittest.main()
