"""
`hardware_check.py` aur voice API ka CONTRACT test.

⚠️ YE FILE EK ASLI GALTI SE BANI HAI.

Kya hua tha: maine (AI ne) `hardware_check.py` likha aur usme voice
module ke API naam GUESS kar liye — `Microphone`, `record_seconds`,
`SpeechToText`, `engine.speak()`. Asli naam alag the: `Recorder`,
`record_fixed`, `WhisperSTT`, `engine.say()`.

Sandbox mein bug pakda nahi gaya kyunki wahan mic nahi tha — wo code
path chala hi nahi. User ne asli machine pe chalaya, tab crash hua:

    [FAIL] Recording — ImportError: cannot import name 'Microphone'
    [FAIL] Awaaz bajana — AttributeError: 'TTSEngine' object has no
           attribute 'speak'

SABAK: hardware wala code bhi TEST hona chahiye. Hardware nahi hai to
kam se kam API CONTRACT test karo — ki jo naam use kar rahe ho, wo
sach mein exist karte hain.

Ye tests hardware ke bina chalte hain aur naam badalne pe TURANT fail
ho jaate hain.
"""

from __future__ import annotations

import pathlib

from tests.helpers import SaarthiTestCase, captured_stdout, clean_env

ROOT = pathlib.Path(__file__).resolve().parent.parent


class VoiceApiContract(SaarthiTestCase):
    """
    Voice module ka public API. `hardware_check.py` aur `voice_cli.py`
    dono isi pe depend karte hain.

    Yahan koi naam badle to ye tests fail honge — matlab caller bhi
    update karna padega.
    """

    def test_recorder_class_aur_method_exist_karte_hain(self):
        from saarthi.voice import AudioConfig, Recorder

        self.assertTrue(hasattr(Recorder, "record_fixed"),
                        "Recorder.record_fixed gayab — hardware_check toot jaayega")
        self.assertTrue(hasattr(Recorder, "record_until_silence"))
        # Constructor signature: (config, device)
        recorder = Recorder(AudioConfig())
        self.assertIsNotNone(recorder.config)

    def test_galat_purane_naam_exist_NAHI_karte(self):
        """
        Ye galat naam the jo maine guess kiye the. Agar kabhi in naamon
        se class banayi jaaye to confusion hogi — isliye document kar
        rahe hain ki sahi naam kya hai.
        """
        import saarthi.voice.audio as audio
        import saarthi.voice.stt as stt

        self.assertFalse(hasattr(audio, "Microphone"),
                         "'Microphone' ban gaya? Sahi naam 'Recorder' hai")
        self.assertFalse(hasattr(stt, "SpeechToText"),
                         "'SpeechToText' ban gaya? Sahi naam 'WhisperSTT' hai")

    def test_whisper_stt_class_aur_methods(self):
        from saarthi.voice import WhisperConfig, WhisperSTT

        for method in ("load", "unload", "transcribe", "transcribe_file", "status"):
            self.assertTrue(hasattr(WhisperSTT, method), f"WhisperSTT.{method} gayab")

        self.assertTrue(hasattr(WhisperConfig, "from_env"))
        config = WhisperConfig.from_env()
        self.assertTrue(config.model_size)

    def test_transcript_result_ke_fields(self):
        """hardware_check in fields ko padhta hai."""
        from saarthi.voice.stt import TranscriptResult

        transcript = TranscriptResult(text="paytm kholo", raw_text="pay time cholo")
        for field in ("text", "raw_text", "is_usable", "reject_reason", "speed_ratio"):
            self.assertTrue(hasattr(transcript, field), f"TranscriptResult.{field} gayab")

        self.assertEqual(transcript.text, "paytm kholo")
        self.assertIsInstance(transcript.speed_ratio, float)

    def test_tts_engine_ka_api(self):
        from saarthi.voice import TTSEngine

        self.assertTrue(hasattr(TTSEngine, "say"),
                        "TTSEngine.say gayab — hardware_check toot jaayega")
        self.assertFalse(hasattr(TTSEngine, "speak"),
                         "TTSEngine.speak ban gaya? Sahi naam 'say' hai")
        self.assertTrue(hasattr(TTSEngine, "available_backends"))

        engine = TTSEngine()
        self.assertIsNotNone(engine.backend)
        self.assertIsInstance(engine.has_voice, bool)

    def test_backend_pe_speak_hota_hai_engine_pe_say(self):
        """
        Ye confusion ki jadd hai: BACKEND pe `speak()` hai, par ENGINE
        pe `say()`. Dono alag hain — isliye galti hui thi.
        """
        from saarthi.voice import TTSEngine
        from saarthi.voice.tts import TTSBackend

        self.assertTrue(hasattr(TTSBackend, "speak"), "backend pe speak hona chahiye")
        self.assertTrue(hasattr(TTSEngine, "say"), "engine pe say hona chahiye")

    def test_available_backends_ka_shape(self):
        """hardware_check aur voice_cli ise unpack karte hain."""
        from saarthi.voice import TTSEngine

        backends = TTSEngine.available_backends()
        self.assertTrue(backends)
        for item in backends:
            self.assertEqual(len(item), 3, "(name, available, quality) hona chahiye")
            name, available, quality = item
            self.assertIsInstance(name, str)
            self.assertIsInstance(available, bool)
            self.assertIsInstance(quality, str)

    def test_helper_functions_exist_karte_hain(self):
        from saarthi.voice import (
            audio_setup_help,
            available_wake_modes,
            is_audio_available,
            is_stt_available,
            list_input_devices,
            recommend_model_size,
            stt_setup_help,
        )

        self.assertIsInstance(is_audio_available(), bool)
        self.assertIsInstance(is_stt_available(), bool)
        self.assertIsInstance(list_input_devices(), list)
        self.assertTrue(recommend_model_size())
        self.assertTrue(audio_setup_help())
        self.assertTrue(stt_setup_help())

        for name, available, description in available_wake_modes():
            self.assertIsInstance(name, str)
            self.assertIsInstance(available, bool)
            self.assertTrue(description.strip(), f"'{name}' ka description khali")


class HardwareCheckScript(SaarthiTestCase):
    """Script import ho aur non-interactive checks crash na karein."""

    def load_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "hardware_check", ROOT / "hardware_check.py"
        )
        module = importlib.util.module_from_spec(spec)
        with captured_stdout():
            spec.loader.exec_module(module)
        return module

    def test_script_import_hota_hai(self):
        self.assertIsNotNone(self.load_module())

    def test_saare_check_functions_maujood_hain(self):
        module = self.load_module()
        for name in (
            "check_system", "check_install", "check_keys", "check_mic",
            "check_speaker", "check_phone", "check_browser",
            "print_summary", "main", "say", "section", "result",
        ):
            self.assertTrue(hasattr(module, name), f"{name}() gayab")

    def test_non_interactive_checks_crash_nahi_karte(self):
        module = self.load_module()

        with clean_env(NVIDIA_API_KEY="nvapi-fake-for-test"):
            for name in ("check_system", "check_install", "check_keys", "check_browser"):
                module.REPORT.clear()
                with captured_stdout():
                    try:
                        getattr(module, name)()
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"{name}() crash hua: {type(exc).__name__}: {exc}")

    def test_mic_aur_speaker_non_interactive_mode_mein_crash_nahi_karte(self):
        module = self.load_module()
        module.REPORT.clear()
        with captured_stdout():
            try:
                module.check_mic(interactive=False)
                module.check_speaker(interactive=False)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"crash hua: {type(exc).__name__}: {exc}")

    def test_result_teen_state_deta_hai(self):
        """PASS / FAIL / SKIP — SKIP ko FAIL nahi maanna."""
        module = self.load_module()
        module.REPORT.clear()
        with captured_stdout():
            module.result("a", True)
            module.result("b", False)
            module.result("c", None)

        joined = "\n".join(module.REPORT)
        self.assertIn("[PASS] a", joined)
        self.assertIn("[FAIL] b", joined)
        self.assertIn("[SKIP] c", joined)

    def test_summary_sirf_FAIL_pe_non_zero_deta_hai(self):
        module = self.load_module()

        module.REPORT.clear()
        with captured_stdout():
            module.result("ok", True)
            module.result("skipped", None)
            code = module.print_summary()
        self.assertEqual(code, 0, "SKIP ko FAIL maan liya")

        module.REPORT.clear()
        with captured_stdout():
            module.result("broken", False)
            code = module.print_summary()
        self.assertEqual(code, 1)

    def test_api_keys_ki_value_kabhi_print_nahi_hoti(self):
        """
        Ye security test hai. Report user copy-paste karke bhejta hai —
        usme key nikal jaaye to compromise ho jaayegi.
        """
        module = self.load_module()
        secret = "nvapi-SUPER-SECRET-DO-NOT-LEAK-12345"

        with clean_env(NVIDIA_API_KEY=secret):
            module.REPORT.clear()
            with captured_stdout() as out:
                module.check_keys()

            joined = "\n".join(module.REPORT) + out.getvalue()
            self.assertNotIn(secret, joined, "API KEY REPORT MEIN LEAK HO GAYI!")
            self.assertNotIn(secret[:20], joined, "key ka hissa bhi leak hua!")


class WrappersActuallyRun(SaarthiTestCase):
    """
    ⭐ YE TESTS ASLI BUG PAKADTE HAIN.

    Pehle maine sirf voice API ko alag se test kiya tha — wo pass hota
    tha, par bug phir bhi nikal gaya. Kyunki galat naam
    `hardware_check.py` ke ANDAR the, aur wo code path test mein chalta
    hi nahi tha.

    Ab wrappers ko SEEDHA call karte hain. Naam galat hua to ye tests
    turant fail honge — hardware ke bina bhi.
    """

    def load_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "hardware_check", ROOT / "hardware_check.py"
        )
        module = importlib.util.module_from_spec(spec)
        with captured_stdout():
            spec.loader.exec_module(module)
        return module

    def test_open_recorder_sahi_class_use_karta_hai(self):
        """Bug #1: `Microphone` instead of `Recorder` — ye pakadta hai."""
        from saarthi.voice import Recorder

        module = self.load_module()
        recorder = module.open_recorder()   # <- yahan ImportError aayega
        self.assertIsInstance(recorder, Recorder)

    def test_record_seconds_sahi_method_use_karta_hai(self):
        """Bug: `record_seconds()` instead of `record_fixed()`."""
        module = self.load_module()

        calls = []

        class FakeRecorder:
            def record_fixed(self, seconds):
                calls.append(seconds)
                return [0, 1, 2]

            def record_until_silence(self, on_status=None):
                raise AssertionError("galat method call hui")

        samples = module.record_seconds(FakeRecorder(), 3.0)
        self.assertEqual(calls, [3.0], "record_fixed() call nahi hui")
        self.assertEqual(samples, [0, 1, 2])

    def test_open_stt_sahi_class_use_karta_hai(self):
        """Bug: `SpeechToText` instead of `WhisperSTT`."""
        from saarthi.voice import WhisperSTT

        module = self.load_module()
        stt = module.open_stt()   # model load nahi hota, sirf construct
        self.assertIsInstance(stt, WhisperSTT)

    def test_speak_text_sahi_method_use_karta_hai(self):
        """
        Bug #2: `engine.speak()` instead of `engine.say()` — ye pakadta hai.

        NullTTS backend hamesha available hai, isliye ye test bina
        speaker ke bhi chalta hai.
        """
        from saarthi.voice import TTSEngine

        module = self.load_module()
        with captured_stdout():
            module.speak_text(TTSEngine(), "test")   # <- AttributeError aayega

    def test_speak_text_engine_ka_say_call_karta_hai_backend_ka_speak_nahi(self):
        module = self.load_module()
        calls = []

        class FakeEngine:
            def say(self, text, prepare=True):
                calls.append(text)
                return True

            def speak(self, text):
                raise AssertionError(
                    "engine.speak() call hui — engine pe `say()` hota hai, "
                    "`speak()` backend pe hota hai"
                )

        module.speak_text(FakeEngine(), "namaste")
        self.assertEqual(calls, ["namaste"])


class ImportsResolve(SaarthiTestCase):
    """
    Har entrypoint ke SAARE `from saarthi... import X` resolve hone
    chahiye — chahe wo function ke andar likhe hon.

    Function ke andar wale imports sabse khatarnak hain: wo sirf tab
    fail hote hain jab wo function chalta hai. Agar wo code path
    hardware ke bina nahi chalta, to bug user tak pahunch jaata hai.
    Yahi hua tha.

    Ye test AST se saare imports nikaal ke check karta hai — code
    chalane ki zarurat nahi.
    """

    FILES = ("hardware_check.py", "cli.py", "voice_cli.py", "run_tests.py")

    def saarthi_imports(self, path: pathlib.Path):
        """(module, name, line) — sirf saarthi ke imports."""
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "saarthi" or module.startswith("saarthi."):
                    for alias in node.names:
                        found.append((module, alias.name, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("saarthi"):
                        found.append((alias.name, None, node.lineno))

        return found

    def test_saare_saarthi_imports_resolve_hote_hain(self):
        import importlib

        checked = 0
        for filename in self.FILES:
            path = ROOT / filename
            if not path.exists():
                continue

            for module_name, symbol, lineno in self.saarthi_imports(path):
                try:
                    module = importlib.import_module(module_name)
                except ImportError as exc:
                    self.fail(f"{filename}:{lineno} — '{module_name}' import nahi hua: {exc}")

                if symbol is not None:
                    self.assertTrue(
                        hasattr(module, symbol),
                        f"{filename}:{lineno} — '{symbol}' "
                        f"'{module_name}' mein NAHI hai. "
                        f"Naam badal gaya hai ya galat likha hai.",
                    )
                checked += 1

        self.assertGreater(checked, 10, "itne kam imports? AST parsing toot gayi lagti hai")

    def test_ye_test_asli_bug_pakadta_hai(self):
        """
        Meta-test: verify karo ki upar wala test SACH MEIN kaam karta hai.

        Ek jhoota import banake dekho ki wo pakda jaata hai. Warna
        "test pass ho raha hai" ka jhoota bharosa ban jaata hai.
        """
        import ast
        import importlib

        source = "def f():\n    from saarthi.voice import Microphone\n"
        tree = ast.parse(source)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))

        module = importlib.import_module(node.module)
        self.assertFalse(
            hasattr(module, node.names[0].name),
            "'Microphone' exist karta hai? Phir test ka logic galat hai",
        )


class ScriptsCompile(SaarthiTestCase):
    """Saare entrypoints compile hone chahiye."""

    def test_entrypoints_compile_hote_hain(self):
        import py_compile

        for name in ("cli.py", "voice_cli.py", "run_tests.py", "hardware_check.py"):
            try:
                py_compile.compile(str(ROOT / name), doraise=True)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"{name} compile nahi hua: {exc}")
