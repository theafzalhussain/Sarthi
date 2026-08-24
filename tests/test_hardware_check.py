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



class MicDeviceSelection(SaarthiTestCase):
    """
    BUG#10 — galat mic device select hota tha.

    Asli problem (user ki Windows machine pe mili):
        21 input devices the. System default "Microsoft Sound Mapper -
        Input" tha — ek legacy MME wrapper. Usse recording AATI thi par
        peak sirf 303 (out of 32767) = practically silence. Whisper ne
        khali string return ki. Lagta tha voice tuta hua hai, jabki
        sirf galat device select tha.

    Aur asli wajah: `AudioConfig` mein device field HI NAHI THA, aur
    `Recorder` config ka device dekhta hi nahi tha. Matlab mic chunne
    ka koi tareeka hi nahi tha.
    """

    def test_audio_config_mein_device_field_hai(self):
        from saarthi.voice import AudioConfig

        config = AudioConfig()
        self.assertTrue(
            hasattr(config, "device"),
            "AudioConfig.device gayab — mic chunne ka koi tareeka nahi hoga",
        )
        self.assertIsNone(config.device, "default system default hona chahiye")

    def test_audio_config_from_env_exist_karta_hai(self):
        from saarthi.voice import AudioConfig

        self.assertTrue(hasattr(AudioConfig, "from_env"))
        with clean_env():
            self.assertIsNone(AudioConfig.from_env().device)

    def test_env_se_device_index_set_hota_hai(self):
        from saarthi.voice import AudioConfig

        with clean_env(SAARTHI_MIC_DEVICE="5"):
            self.assertEqual(AudioConfig.from_env().device, 5)

    def test_env_se_min_threshold_set_hota_hai(self):
        from saarthi.voice import AudioConfig

        with clean_env(SAARTHI_MIC_MIN_THRESHOLD="150"):
            self.assertEqual(AudioConfig.from_env().min_threshold, 150.0)

        # Galat value pe crash nahi — default rehna chahiye
        with clean_env(SAARTHI_MIC_MIN_THRESHOLD="bakwaas"):
            self.assertEqual(AudioConfig.from_env().min_threshold, 300.0)

    def test_recorder_config_ka_device_use_karta_hai(self):
        """
        Ye asli bug tha: Recorder config.device ko IGNORE karta tha,
        isliye SAARTHI_MIC_DEVICE set karne ka koi asar nahi hota tha.
        """
        from saarthi.voice import AudioConfig, Recorder

        config = AudioConfig()
        config.device = 7
        recorder = Recorder(config)
        self.assertEqual(
            recorder.device, 7,
            "Recorder ne config.device ignore kar diya — mic setting bekaar hai",
        )

    def test_explicit_device_param_config_se_jeetta_hai(self):
        from saarthi.voice import AudioConfig, Recorder

        config = AudioConfig()
        config.device = 7
        self.assertEqual(Recorder(config, device=3).device, 3)

    def test_recorder_pe_peak_level_hai(self):
        """Live level meter ke liye — user ko dikhna chahiye awaaz aa rahi hai."""
        from saarthi.voice import Recorder

        self.assertTrue(
            hasattr(Recorder, "peak_level"),
            "Recorder.peak_level gayab — live level meter nahi chalega",
        )

    def test_input_devices_structured_data_deta_hai(self):
        from saarthi.voice import input_devices

        devices = input_devices()
        self.assertIsInstance(devices, list)
        for device in devices:
            for key in ("index", "name", "channels", "api", "is_default"):
                self.assertIn(key, device, f"'{key}' gayab")
            self.assertIsInstance(device["index"], int)
            self.assertIsInstance(device["is_default"], bool)

    def test_purana_list_input_devices_api_bacha_hua_hai(self):
        """voice_cli.py aur hardware_check isko use karte hain."""
        from saarthi.voice import list_input_devices

        for item in list_input_devices():
            self.assertTrue(item.startswith("["), f"format badal gaya: {item!r}")

    def test_resolve_device_index_handle_karta_hai(self):
        from saarthi.voice import resolve_device

        self.assertEqual(resolve_device("5"), 5)
        self.assertEqual(resolve_device(5), 5)
        self.assertEqual(resolve_device("  12  "), 12)

    def test_resolve_device_khali_pe_none_deta_hai(self):
        from saarthi.voice import resolve_device

        for value in (None, "", "   "):
            self.assertIsNone(resolve_device(value))

    def test_resolve_device_anjaan_naam_pe_crash_nahi_karta(self):
        """Fail-safe: galat naam pe system default pe gir jao, crash nahi."""
        from saarthi.voice import resolve_device

        self.assertIsNone(resolve_device("aisa koi mic nahi hai 12345"))

    def test_describe_device_padhne_layak_hai(self):
        from saarthi.voice import describe_device

        self.assertTrue(describe_device(None).strip())
        self.assertIn("999", describe_device(999))


class LevelMeter(SaarthiTestCase):
    """
    Level bar — user ko DIKHNA chahiye ki awaaz register ho rahi hai.

    Recording ke BAAD ek number dikhana kaafi nahi tha; user ko pata
    hi nahi chalta ki bolte waqt kuch aa raha hai ya nahi.
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

    def test_level_bar_har_range_ka_verdict_deta_hai(self):
        module = self.load_module()

        cases = [
            (0, "kuch nahi"),
            (299, "kuch nahi"),
            (303, "bahut dheema"),   # user ka asli peak
            (1499, "bahut dheema"),
            (2000, "theek"),
            (6000, "accha"),
        ]
        for peak, expected in cases:
            bar = module.level_bar(peak)
            self.assertIn(expected, bar, f"peak {peak} ka verdict galat: {bar}")
            self.assertIn(str(peak), bar)

    def test_level_bar_width_respect_karta_hai(self):
        module = self.load_module()
        bar = module.level_bar(1000, width=10)
        inside = bar[bar.index("[") + 1 : bar.index("]")]
        self.assertEqual(len(inside), 10)

    def test_bahut_bada_peak_bar_todta_nahi(self):
        module = self.load_module()
        bar = module.level_bar(999999, width=20)
        inside = bar[bar.index("[") + 1 : bar.index("]")]
        self.assertEqual(len(inside), 20)

    def test_peak_level_wrapper_sahi_method_call_karta_hai(self):
        module = self.load_module()
        calls = []

        class FakeRecorder:
            def peak_level(self, seconds):
                calls.append(seconds)
                return 1234

        self.assertEqual(module.peak_level(FakeRecorder(), 0.5), 1234)
        self.assertEqual(calls, [0.5])

    def test_open_recorder_device_param_leta_hai(self):
        """--mic-scan har device ke liye recorder banata hai."""
        module = self.load_module()
        recorder = module.open_recorder(device=3)
        self.assertEqual(recorder.device, 3)

    def test_scan_mics_function_maujood_hai(self):
        module = self.load_module()
        self.assertTrue(hasattr(module, "scan_mics"))

    def test_mic_scan_flag_wire_hua_hai(self):
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn('"--mic-scan"', source)
        self.assertIn("scan_mics()", source)



class RamDetection(SaarthiTestCase):
    """
    BUG#13 — RAM detection Windows pe kaam hi nahi karta tha.

    Purana code sirf do tareeke use karta tha:
        /proc/meminfo          -> Linux only
        os.sysconf(...)        -> Unix only (Windows pe AttributeError)

    Nateeja: Windows pe HAMESHA 0 return hota tha, aur
    recommend_model_size() "base" pe atak jaata tha — chahe machine
    mein 32GB RAM ho.

    User ki machine: 31GB RAM, par tool "base" suggest kar raha tha.
    Aur "base" Hinglish pe kamzor hai — usne "paytm kholo" ko
    "Kya kya ouri website, proper da yaar uca" suna.
    """

    def test_ram_detect_hota_hai(self):
        from saarthi.voice import total_ram_gb

        ram = total_ram_gb()
        self.assertGreater(
            ram, 0.0,
            "RAM detect nahi hui — is platform ke liye branch missing hai",
        )
        self.assertLess(ram, 10000, f"RAM ka number galat lag raha hai: {ram}")

    def test_windows_branch_code_mein_hai(self):
        """
        Windows pe test nahi chala sakte, par code path maujood hona
        chahiye. Yahi BUG#13 tha — branch hi nahi tha.
        """
        import inspect

        from saarthi.voice.stt import total_ram_gb

        source = inspect.getsource(total_ram_gb)
        self.assertIn("GlobalMemoryStatusEx", source, "Windows branch gayab")
        self.assertIn("darwin", source, "macOS branch gayab")
        self.assertIn("/proc/meminfo", source, "Linux branch gayab")

    def test_ram_ke_hisaab_se_model_chunta_hai(self):
        import saarthi.voice.stt as stt

        original = stt.total_ram_gb
        try:
            cases = [
                (2.0, "tiny"),
                (4.0, "base"),
                (8.0, "small"),
                (16.0, "medium"),
                (31.0, "medium"),
                (0.0, "base"),   # pata nahi chala -> safe default
            ]
            for ram, expected in cases:
                stt.total_ram_gb = lambda r=ram: r
                self.assertEqual(
                    stt.recommend_model_size(), expected,
                    f"{ram}GB pe '{expected}' chahiye tha",
                )
        finally:
            stt.total_ram_gb = original

    def test_bade_ram_pe_base_nahi_suggest_karta(self):
        """
        Ye BUG#13 ka core hai: 31GB RAM pe 'base' suggest karna galat
        hai, kyunki base Hinglish pe kamzor hai.
        """
        import saarthi.voice.stt as stt

        original = stt.total_ram_gb
        try:
            stt.total_ram_gb = lambda: 31.0
            self.assertNotEqual(
                stt.recommend_model_size(), "base",
                "31GB RAM pe 'base' suggest ho raha hai — BUG#13 wapas",
            )
        finally:
            stt.total_ram_gb = original


class LanguageOverride(SaarthiTestCase):
    """
    `transcribe(language=...)` override — `--stt-tune` ke liye zaroori.

    Iske bina har language variant ke liye model dobara load karna
    padta (dheema). Ab ek load, teen variants.
    """

    def test_transcribe_language_param_leta_hai(self):
        import inspect

        from saarthi.voice import WhisperSTT

        params = list(inspect.signature(WhisperSTT.transcribe).parameters)
        self.assertIn("language", params, "language override param gayab")

    def test_sentinel_none_se_alag_hai(self):
        """
        `None` ka apna matlab hai (auto-detect), isliye "kuch diya hi
        nahi" ke liye alag sentinel chahiye.
        """
        from saarthi.voice.stt import _USE_CONFIG

        self.assertIsNotNone(_USE_CONFIG)
        self.assertIsNot(_USE_CONFIG, None)

    def test_config_ka_language_default_rehta_hai(self):
        import inspect

        from saarthi.voice import WhisperSTT

        source = inspect.getsource(WhisperSTT.transcribe)
        self.assertIn("_USE_CONFIG", source)
        self.assertIn("self.config.language", source)


class SttTuning(SaarthiTestCase):
    """`--stt-tune` — guess ke bajaay measure karo."""

    def load_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "hardware_check", ROOT / "hardware_check.py"
        )
        module = importlib.util.module_from_spec(spec)
        with captured_stdout():
            spec.loader.exec_module(module)
        return module

    def test_similarity_sahi_score_deta_hai(self):
        module = self.load_module()
        expected = "paytm kholo"

        self.assertEqual(module.similarity("paytm kholo", expected), 1.0)
        self.assertEqual(module.similarity("Paytm kholo.", expected), 1.0,
                         "case/punctuation ignore hona chahiye")
        self.assertEqual(module.similarity("", expected), 0.0)

        # User ka asli garbage output — kam score aana chahiye
        garbage = "Kya kya ouri website, proper da yaar uca."
        self.assertLess(module.similarity(garbage, expected), 0.4)

        # ASR correction se pehle ka — thoda match karega
        partial = module.similarity("pay time cholo", expected)
        self.assertGreater(partial, 0.4)
        self.assertLess(partial, 1.0)

    def test_similarity_none_pe_crash_nahi_karta(self):
        module = self.load_module()
        self.assertEqual(module.similarity(None, "paytm kholo"), 0.0)
        self.assertEqual(module.similarity("x", None), 0.0)

    def test_scan_stt_function_maujood_hai(self):
        module = self.load_module()
        self.assertTrue(hasattr(module, "scan_stt"))
        self.assertTrue(hasattr(module, "TUNE_PHRASE"))

    def test_stt_tune_flag_wire_hua_hai(self):
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn('"--stt-tune"', source)
        self.assertIn("scan_stt()", source)

    def test_quality_signals_dikhte_hain(self):
        """
        Galat suna kyun — ye batane ke liye avg_logprob aur detected
        language dikhna zaroori hai. Pehle sirf text dikhta tha.
        """
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn("avg_logprob", source)
        self.assertIn("no_speech_prob", source)
        self.assertIn("language_probability", source)



class Bug19BiasingContaminatesOutput(SaarthiTestCase):
    """
    BUG#19 — biasing prompt OUTPUT KHARAAB kar raha tha (BUG#14 ka bacha hua hissa).

    BUG#14 mein prompt se SENTENCES hataye the. Par user ki machine pe
    phir bhi ye hua (audio PERFECT, peak 27506):

        bola : "paytm kholo"
        suna : 'Open YouTube'
        suna : 'Open, Growman'

    "YouTube" aur "Groww" DONO hamare PRIORITY_APPS mein hain, aur
    output mein COMMA bhi tha — matlab Whisper ne prompt ki comma-wali
    LIST hi wapas ugal di.

    Matlab sirf sentences hataana kaafi nahi tha. Whisper ka
    initial_prompt chhote command ("paytm kholo" = 1 second) pe ULTA
    nuksaan karta hai.

    FIX: `WHISPER_BIASING` setting, DEFAULT OFF. Pillar #1 ka asli kaam
    correction layer (65 regex rules) karta hai — wo transcribe ke BAAD
    chalta hai aur hallucinate nahi karata.
    """

    def test_bug19_biasing_default_off_hai(self):
        from saarthi.voice import WhisperConfig

        with clean_env():
            self.assertEqual(
                WhisperConfig.from_env().biasing, "off",
                "Biasing default ON hai — output contaminate hoga",
            )

    def test_bug19_biasing_env_se_on_ho_sakti_hai(self):
        from saarthi.voice import WhisperConfig

        with clean_env(WHISPER_BIASING="vocab"):
            self.assertEqual(WhisperConfig.from_env().biasing, "vocab")

    def test_bug19_galat_value_pe_off(self):
        from saarthi.voice import WhisperConfig

        for value in ("bakwaas", "true", "yes", ""):
            with clean_env(WHISPER_BIASING=value):
                self.assertEqual(WhisperConfig.from_env().biasing, "off")

    def test_bug19_biasing_off_pe_prompt_none_jaata_hai(self):
        import inspect

        from saarthi.voice import WhisperSTT

        source = inspect.getsource(WhisperSTT.transcribe)
        self.assertIn('self.config.biasing == "vocab"', source)
        self.assertIn("initial_prompt = None", source)

    def test_bug19_correction_layer_zinda_hai(self):
        """
        Biasing off hui, par Pillar #1 ka ASLI engine chalna chahiye.
        Yahi wo hissa hai jo hallucinate nahi karata.
        """
        from saarthi.lang import parse
        from saarthi.voice.hinglish_asr import correct_transcript

        result = correct_transcript("pay time cholo aur die hazaar ka bell bhar do")
        parsed = parse(result.corrected)

        self.assertEqual([a[0] for a in parsed.apps], ["paytm"])
        self.assertEqual(parsed.amount, 2500.0)


class SilenceDetectorDiagnostic(SaarthiTestCase):
    """
    `--mic-live` — `record_until_silence` ke andar ka haal dikhata hai.

    Ek contradiction tha jo main code padh ke solve nahi kar paya:
        record_fixed          -> peak 27506 (LOUD)
        record_until_silence  -> "kuch sunai nahi diya"

    Device passing, rms() ka float64 cast, sample rate, int16->float32
    conversion — sab check kiya, sab sahi the. Isliye guess karna band
    kiya aur INSTRUMENT kiya: ye tool asli noise_floor, threshold aur
    per-chunk rms dikhata hai.
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

    def test_watch_function_maujood_hai(self):
        self.assertTrue(hasattr(self.load_module(), "watch_silence_detector"))

    def test_record_until_silence_ka_contract(self):
        """
        BUG#9 KA CLASS — `watch_silence_detector()` sirf ASLI MIC pe
        chalta hai. Agar maine galat attribute naam likha (jaise
        `status.volume` jabki asli `status.loudness` hai) to sandbox
        mein KABHI pakda nahi jaayega — user ki machine pe crash hoga.

        Isliye contract yahan lock karte hain, bina mic ke.
        """
        import inspect

        from saarthi.voice.audio import DetectorStatus, ListenState, Recorder

        # 1. record_until_silence ek callback leta hai aur TUPLE deta hai
        signature = inspect.signature(Recorder.record_until_silence)
        self.assertIn(
            "on_status", signature.parameters,
            "callback ka naam badal gaya — watch_silence_detector tut jaayega",
        )

        # 2. Jo attributes hum padhte hain wo sach mein hain
        status = DetectorStatus(state=ListenState.WAITING)
        for attribute in ("state", "loudness", "threshold", "got_speech"):
            self.assertTrue(
                hasattr(status, attribute),
                f"DetectorStatus mein '{attribute}' nahi hai",
            )

        # 3. Jo states hum naam se use karte hain wo exist karti hain
        for name in ("CALIBRATING", "WAITING", "SPEAKING", "DONE", "TIMEOUT"):
            self.assertTrue(hasattr(ListenState, name), f"ListenState.{name} gayab")

        # 4. `.value` padhte hain — str Enum hona chahiye
        self.assertEqual(ListenState.WAITING.value, "waiting")

    def test_config_ke_threshold_fields_maujood_hain(self):
        """`watch_silence_detector` teen config fields print karta hai."""
        from saarthi.voice import AudioConfig

        config = AudioConfig()
        for field in ("noise_multiplier", "min_threshold", "speech_start_chunks"):
            self.assertTrue(hasattr(config, field), f"AudioConfig.{field} gayab")

    def test_mic_live_flag_wire_hua_hai(self):
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn('"--mic-live"', source)
        self.assertIn("watch_silence_detector()", source)

    def test_teeno_diagnosis_case_handle_hote_hain(self):
        """
        Teen alag wajah ho sakti hain — teeno ka apna diagnosis chahiye:
          stream khali        -> device/streaming ka issue
          audio < threshold   -> threshold kam karo
          audio > threshold   -> lagatar chunks nahi mile
        """
        import inspect

        module = self.load_module()
        source = inspect.getsource(module.watch_silence_detector)

        self.assertIn("STREAM SE AUDIO HI NAHI AA RAHA", source)
        self.assertIn("THRESHOLD SE KAM", source)
        self.assertIn("SPEECH CONFIRM NAHI HUI", source)
        self.assertIn("SAARTHI_MIC_MIN_THRESHOLD", source)

    def test_stt_tune_countdown_deta_hai(self):
        """
        User message padhta rehta tha aur bolna bhool jaata tha — phir
        Whisper ko aadha shabd milta tha.
        """
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn("AB BOL:", source)

    def test_stt_tune_biasing_aur_mic_live_suggest_karta_hai(self):
        import inspect

        module = self.load_module()
        source = inspect.getsource(module.scan_stt)

        self.assertIn("WHISPER_BIASING", source, "biasing ka shak nahi batata")
        self.assertIn("--mic-live", source, "voice diagnostic suggest nahi karta")


class NextBiggerModel(SaarthiTestCase):
    """
    BUG#20 — `--stt-tune` UPGRADE ke liye WAHI model suggest karta tha.

    User 'small' pe tha. Tool ne kaha:
        "MODEL CHHOTA HAI ('small') ... 'small' try kar"

    Bekaar advice. Ab `next_bigger_model()` alag function hai taaki
    test ise SEEDHA call kar sake.

    (Pehla test sirf source mein "ladder" shabd dhoondhta tha — maine
    bug wapas daala aur wo test PASS HO GAYA, kyunki shabd doosri line
    pe bacha hua tha. Isliye behaviour test likha.)
    """

    def test_har_model_apne_se_bada_deta_hai(self):
        from saarthi.voice.stt import MODEL_LADDER, next_bigger_model

        for current in ("tiny", "base", "small", "medium"):
            bigger = next_bigger_model(current)
            self.assertNotEqual(
                bigger, current, f"{current} ke liye wahi model suggest kiya",
            )
            self.assertGreater(
                MODEL_LADDER.index(bigger), MODEL_LADDER.index(current),
                f"{current} -> {bigger} upgrade nahi hai",
            )

    def test_sabse_bade_pe_wahi_rehta_hai(self):
        """large-v3 se aage kuch nahi — jhoothi advice nahi deni."""
        from saarthi.voice.stt import next_bigger_model

        self.assertEqual(next_bigger_model("large-v3"), "large-v3")

    def test_variants_bhi_handle_hote_hain(self):
        from saarthi.voice.stt import next_bigger_model

        self.assertEqual(next_bigger_model("small.en"), "medium")
        self.assertEqual(next_bigger_model("base.en"), "small")
        self.assertEqual(next_bigger_model("large-v2"), "large-v3")
        self.assertEqual(next_bigger_model("turbo"), "large-v3")

    def test_bakwaas_input_pe_crash_nahi(self):
        from saarthi.voice.stt import MODEL_LADDER, next_bigger_model

        for junk in ("", "   ", "bakwaas", "big"):
            self.assertIn(next_bigger_model(junk), MODEL_LADDER)

    def test_stt_tune_sabse_bade_model_pe_bada_model_suggest_nahi_karta(self):
        """
        `at_top` case: agar user already large-v3 pe hai to advice mein
        "Bada model" nahi hona chahiye.
        """
        import inspect

        module = self.load_module()
        source = inspect.getsource(module.scan_stt)

        self.assertIn("at_top", source, "sabse bade model ka case handle nahi hai")
        self.assertIn("Model badalne se ab kuch nahi hoga", source)

    def load_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "hardware_check", ROOT / "hardware_check.py"
        )
        module = importlib.util.module_from_spec(spec)
        with captured_stdout():
            spec.loader.exec_module(module)
        return module



class StreamConfigScan(SaarthiTestCase):
    """
    `--mic-stream` — BUG#22 ka diagnostic.

    User ki machine pe sd.rec chalta tha par blocking stream.read()
    sirf zeros deta tha. Kaunsa raasta chalega ye code padh ke pata
    nahi chalta — PortAudio ka backend (MME / WASAPI / WDM-KS) har
    machine pe alag behave karta hai. Isliye MEASURE karte hain.
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

    # ------------------------------------------------------------------

    def test_mic_stream_flag_wire_hua_hai(self):
        source = (ROOT / "hardware_check.py").read_text(encoding="utf-8")
        self.assertIn('"--mic-stream"', source)
        self.assertIn("scan_stream_configs()", source)
        self.assertTrue(hasattr(self.load_module(), "scan_stream_configs"))

    def test_peak_int16_scale_pe_aata_hai(self):
        module = self.load_module()
        self.assertEqual(module._probe_peak([100, -5000, 20], "int16"), 5000)

    def test_float32_peak_int16_scale_pe_convert_hota_hai(self):
        """
        ⚠️ YE EK ASLI TRAP HAI.

        float32 stream -1.0..1.0 deta hai, int16 stream 0..32767. Bina
        scale kiye float32 ka peak hamesha 1 se kam aata — aur hamara
        "300 se kam = silence" check usse SILENT bata deta. Ek chalne
        wala config "fail" dikhta.
        """
        module = self.load_module()

        # 0.5 float32 == 16384 int16
        self.assertEqual(module._probe_peak([0.1, -0.5, 0.02], "float32"), 16384)

        # Aur ye 300 ke threshold ke UPAR hona chahiye (silence nahi)
        loud = module._probe_peak([0.4], "float32")
        self.assertGreater(loud, 300, "chalta hua float32 config silent dikhega")

    def test_khali_aur_none_pe_zero(self):
        module = self.load_module()
        for value in (None, [], ()):
            self.assertEqual(module._probe_peak(value, "int16"), 0)

    def test_probe_sounddevice_ke_bina_crash_nahi_karta(self):
        """
        Har probe ka fail hona NORMAL hai — yahi to measure kar rahe
        hain. Ek probe crash kar de to poora scan ruk jaayega aur baaki
        config kabhi try nahi honge.
        """
        from saarthi.voice import AudioConfig

        module = self.load_module()
        config = AudioConfig()

        for probe in (module._probe_stream, module._probe_sd_rec):
            peak, error = probe(None, config)
            self.assertEqual(peak, 0)
            self.assertIsInstance(error, str)

    def test_scan_default_raaste_ko_alag_se_check_karta_hai(self):
        """
        Asli sawaal ye hai: HAMARA default raasta chala ya nahi. Sirf
        "kuch chal gaya" kaafi nahi.
        """
        import inspect

        module = self.load_module()
        source = inspect.getsource(module.scan_stream_configs)

        self.assertIn("default_ok", source)
        self.assertIn("SAARTHI_MIC_BLOCKSIZE", source, "exact .env line nahi deta")
        self.assertIn("SAARTHI_MIC_LATENCY", source)
        # Blocking read bhi test hona chahiye — wahi bug wala raasta hai
        self.assertIn("callback_mode=False", source)


class StreamTuningConfig(SaarthiTestCase):
    """
    `SAARTHI_MIC_BLOCKSIZE` / `SAARTHI_MIC_LATENCY` — BUG#22 ke knob.

    `--mic-stream` measure karke exact line batata hai; ye knob usse
    apply karne ke liye hain. Knob ke bina diagnostic bekaar hai —
    user ko pata chal jaayega kya chalega par lagaa nahi payega.
    """

    def test_blocksize_env_se_aata_hai(self):
        from saarthi.voice import AudioConfig

        with clean_env(SAARTHI_MIC_BLOCKSIZE="0"):
            self.assertEqual(AudioConfig.from_env().blocksize, 0)
        with clean_env(SAARTHI_MIC_BLOCKSIZE="1024"):
            self.assertEqual(AudioConfig.from_env().blocksize, 1024)

    def test_latency_env_se_aata_hai(self):
        from saarthi.voice import AudioConfig

        with clean_env(SAARTHI_MIC_LATENCY="high"):
            self.assertEqual(AudioConfig.from_env().latency, "high")
        with clean_env(SAARTHI_MIC_LATENCY="LOW"):
            self.assertEqual(AudioConfig.from_env().latency, "low")

    def test_bakwaas_value_ignore_hoti_hai(self):
        """Galat value pe crash nahi — default pe raho (BUG#12 ka sabak)."""
        from saarthi.voice import AudioConfig

        for junk in ("bakwaas", "-5", "", "3.5"):
            with clean_env(SAARTHI_MIC_BLOCKSIZE=junk):
                blocksize = AudioConfig.from_env().blocksize
                self.assertTrue(
                    blocksize is None or blocksize >= 0,
                    f"'{junk}' se galat blocksize bana: {blocksize}",
                )
        for junk in ("bakwaas", "medium", "0"):
            with clean_env(SAARTHI_MIC_LATENCY=junk):
                self.assertIsNone(AudioConfig.from_env().latency)

    def test_stream_blocksize_property(self):
        from saarthi.voice import AudioConfig

        config = AudioConfig()
        self.assertEqual(
            config.stream_blocksize, config.chunk_samples,
            "default pe hamara chunk size use hona chahiye",
        )

        config.blocksize = 0
        self.assertEqual(config.stream_blocksize, 0, "0 = PortAudio decide kare")

        config.blocksize = 1024
        self.assertEqual(config.stream_blocksize, 1024)

    def test_record_until_silence_config_use_karta_hai(self):
        """
        Knob ka asar HONA chahiye. `.env` mein set ho par stream tak na
        pahunche — ye BUG#11 ka class hai (setting thi, code mein nahi).
        """
        import inspect

        from saarthi.voice.audio import Recorder

        source = inspect.getsource(Recorder.record_until_silence)
        self.assertIn("stream_blocksize", source, "blocksize knob wire nahi hua")
        self.assertIn("latency", source, "latency knob wire nahi hua")

    def test_latency_sirf_set_hone_pe_bheja_jaata_hai(self):
        """
        `latency=None` bhejna PortAudio ke default se ALAG hota hai.
        Isliye set na ho to key hi nahi jaani chahiye.
        """
        import inspect

        from saarthi.voice.audio import Recorder

        source = inspect.getsource(Recorder.record_until_silence)
        self.assertIn("if self.config.latency:", source)



class SttTuneDiagnosticGaps(SaarthiTestCase):
    """
    BUG#24 — `--stt-tune` ki output se diagnosis nahi ho pa raha tha.

    User ne output bheja:

        [INFO] Abhi ki language setting: en
        language=en    score 23%   "So, you know, it's a YouTube story."
        Rok diya.

    TEEN cheezein missing thi, aur teeno ne diagnosis slow kar diya:

    1. BIASING setting print hi nahi hoti thi. Main bata nahi paya ki
       ye hallucination biasing ki wajah se hai (BUG#19) ya Whisper ka
       apna behaviour (BUG#23). Ek missing INFO line = ek pura round.

    2. CONFIDENCE (logprob / no_speech_prob) nahi dikhta tha. Score 23%
       to dikha, par Whisper ko KHUD pata tha ya nahi — ye nahi.

    3. PROGRESS nahi dikhta tha. 3 variants hote hain, har ek 5-15
       second. User ne pehle ke baad Ctrl+C daba diya ("Rok diya.") —
       usko laga atak gaya. `hi` aur `auto` kabhi try hi nahi hue,
       jabki asli jawab wahan ho sakta tha.
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

    def scan_stt_source(self):
        import inspect

        return inspect.getsource(self.load_module().scan_stt)

    def test_bug24_biasing_setting_print_hoti_hai(self):
        """
        ⚠️ Pehle ye test sirf `"config.biasing" in source` check karta
        tha. Maine print line hata ke verify kiya — test PASS HO GAYA,
        kyunki `if config.biasing != "off":` wali doosri line bachi thi.
        Galat wajah se pass hone wala test bekaar hai.

        Ab wo EXACT label check karte hain jo user ki output mein aana
        chahiye.
        """
        source = self.scan_stt_source()
        self.assertIn(
            "[INFO] Biasing:", source,
            "biasing print nahi hoti — hallucination ki wajah pata nahi chalegi",
        )

    def test_bug24_per_variant_confidence_dikhti_hai(self):
        source = self.scan_stt_source()
        self.assertIn("avg_logprob", source, "logprob nahi dikhta")
        self.assertIn("no_speech_prob", source, "no_speech_prob nahi dikhta")

    def test_bug24_progress_counter_hai(self):
        """
        `[1/3]` transcribe se PEHLE print hona chahiye, baad mein nahi.
        Warna 15 second screen khali rehti hai aur user Ctrl+C dabata hai.
        """
        source = self.scan_stt_source()

        self.assertIn("index}/{total", source, "progress counter nahi hai")
        self.assertIn("chal raha hai...", source, "pehle se message nahi deta")

        # Counter wali line `transcribe` call se PEHLE aani chahiye
        progress_at = source.index("chal raha hai...")
        transcribe_at = source.index("stt.transcribe(samples")
        self.assertLess(
            progress_at, transcribe_at,
            "progress transcribe ke BAAD print ho raha hai — us 15 second "
            "mein screen khali rahegi",
        )

    def test_bug24_kitna_time_lagega_pehle_batata_hai(self):
        source = self.scan_stt_source()
        self.assertIn("Ctrl+C mat dabana", source)

    def test_bug24_reject_reason_dikhta_hai(self):
        """
        Hallucination reject ho (BUG#23) to WAJAH dikhni chahiye, warna
        user ko lagta hai tool ne kuch kiya hi nahi.
        """
        source = self.scan_stt_source()
        self.assertIn("reject_reason", source)
