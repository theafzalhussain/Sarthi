"""
Phase 3 — screenshot caching, multi-phone, ADB retry.

⚠️ YE FILE BAAD MEIN LIKHI GAYI — FEATURES PEHLE AA GAYE THE.

Teeno features implement ho gaye the par EK BHI TEST NAHI THA. Ye
khatarnak tha, khaaskar retry whitelist ke liye: wo SAFETY cheez hai
(`input tap` retry hua to payment pe do baar paisa ja sakta hai), aur
bina test koi bhi usme `shell input` add kar deta aur pata bhi nahi
chalta.

Tests likhte waqt do ASLI BUG mile — dono is file mein locked hain:
  1. dedupe hash sirf pehle 1000 byte pe tha (galat "no change" batata)
  2. SAARTHI_MAX_SCREENSHOTS=0 pe bhi ek image chali jaati thi
"""

from __future__ import annotations

import subprocess

from tests.helpers import SaarthiTestCase, clean_env


# ----------------------------------------------------------------------
#  3c. ADB RETRY — SAFETY. Ye sabse zaroori hissa hai.
# ----------------------------------------------------------------------


class AdbRetrySafety(SaarthiTestCase):
    """
    Retry ka WHITELIST — sirf read-only / idempotent commands.

    🚨 KYUN YE ITNA ZARURI HAI:

    `adb shell input tap 500 900` do baar chala to DO BAAR TAP hoga.
    Payment screen pe wo do baar paisa bhej sakta hai. `input text` do
    baar chala to text do baar type hoga.

    Ye theoretical nahi hai — retry logic add karte waqt sabse natural
    galti yahi hai ki `_adb_raw` mein blanket retry laga do. Isliye
    default DENY hai: jo whitelist mein nahi, uska retry nahi.
    """

    def device(self, serial=None):
        from saarthi.devices.android import AndroidDevice

        return AndroidDevice(name="android", serial=serial)

    # --- Ye retry NAHI hone chahiye ---

    def test_input_tap_KABHI_retry_nahi_hota(self):
        """SABSE ZARURI TEST — double tap = double payment."""
        device = self.device()
        self.assertFalse(
            device._is_retryable(["shell", "input", "tap", "500", "900"]),
            "input tap retry-safe mana gaya — payment pe do baar tap hoga",
        )

    def test_state_badalne_wale_commands_retry_nahi_hote(self):
        device = self.device()
        unsafe = [
            ["shell", "input", "tap", "100", "200"],
            ["shell", "input", "swipe", "1", "2", "3", "4"],
            ["shell", "input", "text", "hello"],
            ["shell", "input", "keyevent", "KEYCODE_ENTER"],
            ["shell", "am", "start", "-n", "com.app/.Main"],
            ["shell", "am", "force-stop", "com.app"],
            ["shell", "monkey", "-p", "com.app", "1"],
            ["shell", "rm", "-f", "/sdcard/x"],
            ["shell", "pm", "uninstall", "com.app"],
            ["install", "app.apk"],
        ]
        for args in unsafe:
            with self.subTest(cmd=" ".join(args)):
                self.assertFalse(
                    device._is_retryable(args),
                    f"'{' '.join(args)}' retry-safe mana gaya — ye state badalta hai",
                )

    def test_arbitrary_shell_command_retry_nahi_hota(self):
        """
        `run_shell()` se LLM/user kuch bhi bhej sakta hai. Uska
        idempotent hona guarantee nahi — default deny.
        """
        device = self.device()
        for command in ("shell echo hi > /sdcard/f", "shell dd if=/dev/zero of=/x"):
            with self.subTest(cmd=command):
                self.assertFalse(device._is_retryable(command.split()))

    # --- Ye retry hone chahiye ---

    def test_read_only_commands_retry_safe_hain(self):
        device = self.device()
        safe = [
            ["devices"],
            ["shell", "getprop", "ro.product.model"],
            ["shell", "wm", "size"],
            ["shell", "dumpsys", "battery"],
            ["exec-out", "screencap", "-p"],
            ["shell", "uiautomator", "dump", "/sdcard/ui.xml"],
            ["shell", "pm", "list", "packages"],
        ]
        for args in safe:
            with self.subTest(cmd=" ".join(args)):
                self.assertTrue(
                    device._is_retryable(args),
                    f"'{' '.join(args)}' read-only hai, retry hona chahiye",
                )

    def test_whitelist_default_DENY_hai(self):
        """Naya/anjaan command apne aap retry-safe na ban jaaye."""
        device = self.device()
        for args in (["kuchbhi"], ["shell", "naya_command"], []):
            with self.subTest(cmd=args):
                self.assertFalse(device._is_retryable(args))

    def test_serial_lagne_pe_bhi_whitelist_sahi_kaam_karti_hai(self):
        """
        `_build_args` aage `-s <serial>` jodta hai. Whitelist match us
        prefix se confuse nahi hona chahiye — warna multi-phone setup pe
        `input tap` chup-chaap retry-able ban jaayega.
        """
        device = self.device(serial="ABC123")

        self.assertFalse(device._is_retryable(["shell", "input", "tap", "1", "2"]))
        self.assertTrue(device._is_retryable(["shell", "dumpsys", "battery"]))

        # aur confirm karo ki serial sach mein lagta hai
        built = device._build_args(["shell", "input", "tap", "1", "2"])
        self.assertIn("-s", built)
        self.assertIn("ABC123", built)

    def test_serial_na_ho_to_dash_s_nahi_lagta(self):
        built = self.device()._build_args(["devices"])
        self.assertNotIn("-s", built)

    # --- Permanent errors ---

    def test_permanent_error_pe_retry_bekaar_hai(self):
        device = self.device()
        for text in (
            "error: device not found",
            "error: device unauthorized",
            "error: no devices/emulators found",
            "adb: device offline",
        ):
            with self.subTest(err=text):
                self.assertTrue(
                    device._is_permanent_error(text),
                    f"'{text}' permanent hai — retry se theek nahi hoga",
                )

    def test_temporary_error_permanent_nahi_mana_jaata(self):
        device = self.device()
        self.assertFalse(device._is_permanent_error("timeout expired"))
        self.assertFalse(device._is_permanent_error(""))


# ----------------------------------------------------------------------
#  3b. MULTI-PHONE
# ----------------------------------------------------------------------


class FakeCompleted:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class MultiPhoneSupport(SaarthiTestCase):
    """
    `adb -s <serial>` ka code pehle se tha, par koi serial pass hi nahi
    karta tha. Do phone lagao to adb khud confuse ho jaata tha.

    Ye tests asli `adb` par depend NAHI karte — subprocess fake hota hai.
    Sandbox/CI mein adb nahi hota, aur test wahan bhi chalna chahiye.
    """

    def fake_adb(self, stdout, returncode=0):
        """`subprocess.run` ko fake karo aur `shutil.which` ko bhi."""
        import contextlib
        import shutil
        from unittest import mock

        @contextlib.contextmanager
        def patched():
            with mock.patch.object(
                subprocess, "run", return_value=FakeCompleted(stdout, returncode)
            ), mock.patch.object(shutil, "which", return_value="/usr/bin/adb"):
                yield

        return patched()

    def test_do_phone_ke_serials_milte_hain(self):
        from saarthi.devices.android import list_adb_serials

        output = (
            "List of devices attached\n"
            "ABC123\tdevice\n"
            "XYZ789\tdevice\n"
        )
        with self.fake_adb(output):
            self.assertEqual(list_adb_serials(), ["ABC123", "XYZ789"])

    def test_offline_aur_unauthorized_skip_hote_hain(self):
        """
        Ye asli scenario hai: user ne cable lagaya par phone pe 'Allow'
        nahi dabaya. Wo device `unauthorized` dikhta hai. Usko register
        karna bekaar hai — har command fail hogi.
        """
        from saarthi.devices.android import list_adb_serials

        output = (
            "List of devices attached\n"
            "GOOD1\tdevice\n"
            "BAD1\toffline\n"
            "BAD2\tunauthorized\n"
        )
        with self.fake_adb(output):
            self.assertEqual(list_adb_serials(), ["GOOD1"])

    def test_koi_phone_na_ho_to_khali_list(self):
        from saarthi.devices.android import list_adb_serials

        with self.fake_adb("List of devices attached\n\n"):
            self.assertEqual(list_adb_serials(), [])

    def test_adb_installed_na_ho_to_crash_NAHI(self):
        """
        Sabse common case — adb install hi nahi hai. Startup pe crash
        bilkul nahi hona chahiye.
        """
        import shutil
        from unittest import mock

        from saarthi.devices.android import list_adb_serials

        with mock.patch.object(shutil, "which", return_value=None):
            self.assertEqual(list_adb_serials("adb"), [])

    def test_adb_timeout_pe_crash_NAHI(self):
        """
        `adb devices` kabhi kabhi hang hota hai (server start ho raha
        ho). Startup tab bhi nahi rukna chahiye.
        """
        import shutil
        from unittest import mock

        from saarthi.devices.android import list_adb_serials

        with mock.patch.object(shutil, "which", return_value="/usr/bin/adb"), \
                mock.patch.object(
                    subprocess, "run",
                    side_effect=subprocess.TimeoutExpired("adb", 3.0),
                ):
            self.assertEqual(list_adb_serials(), [])

    def test_adb_fail_ho_to_khali_list(self):
        from saarthi.devices.android import list_adb_serials

        with self.fake_adb("", returncode=1):
            self.assertEqual(list_adb_serials(), [])

    def test_serial_wala_device_ban_sakta_hai(self):
        from saarthi.devices.android import AndroidDevice

        device = AndroidDevice(name="android-abc123", serial="ABC123")
        self.assertEqual(device.serial, "ABC123")
        self.assertEqual(device.kind, "android")

    def test_android_naam_HAMESHA_kaam_karta_hai(self):
        """
        ⚠️ BACKWARD COMPATIBILITY — ye tootna nahi chahiye.

        `saarthi/lang/lexicon.py` ka `detect_target_device` "android"
        return karta hai, system prompt mein "android" likha hai, aur
        purane skills "android" reference karte hain. Multi-phone add
        karte waqt agar sirf `android-<serial>` register hota to ye sab
        chup-chaap tut jaata.
        """
        from saarthi.config import Settings
        from saarthi.devices.manager import DeviceManager

        with clean_env():
            manager = DeviceManager(Settings.load())
            manager.setup_defaults()

        self.assertIsNotNone(
            manager.get("android"),
            "'android' naam se device nahi mila — purane skills tut jaayenge",
        )
        self.assertIsNotNone(manager.get("desktop"))
        self.assertIsNotNone(manager.get("browser"))


# ----------------------------------------------------------------------
#  3a. SCREENSHOT CACHING
# ----------------------------------------------------------------------


class ScreenshotCaching(SaarthiTestCase):
    """
    Har screenshot message list mein pada rehta tha aur kabhi hataya
    nahi jaata tha. 6 screenshot = chhathi LLM call mein 6 images.
    Free tier ki rate limit yahi se lagti thi.
    """

    def test_max_screenshots_setting_maujood_hai(self):
        from saarthi.config import Settings

        with clean_env():
            settings = Settings.load()
        self.assertEqual(settings.max_screenshots, 2)
        self.assertTrue(settings.screenshot_dedupe)

    def test_env_se_badal_sakta_hai(self):
        from saarthi.config import Settings

        with clean_env(SAARTHI_MAX_SCREENSHOTS="5",
                       SAARTHI_SCREENSHOT_DEDUPE="false"):
            settings = Settings.load()
        self.assertEqual(settings.max_screenshots, 5)
        self.assertFalse(settings.screenshot_dedupe)

    # --- Bug #1: hash truncation ---

    def test_dedupe_POORA_image_hash_karta_hai(self):
        """
        ⚠️ ASLI BUG — hash sirf pehle 1000 byte pe tha:
            hashlib.sha256(image_b64.encode()[:1000])

        Do alag screenshot ka shuruaati data same ho sakta hai (same
        app, same size, badlav neeche ki taraf). Tab hum jhooth bolte —
        "screen mein koi badlav nahi hua" — jabki screen badal gayi thi.
        Agent phir wahi kaam dohraata ya haar maan leta.

        Ye test do image banata hai jinke pehle 2000 characters BILKUL
        same hain par aakhir alag hai. Truncated hash inko same batata
        hai; poora hash alag.
        """
        import ast
        import inspect
        import textwrap

        from saarthi.agent import Agent

        # AST se check karte hain, plain text se NAHI.
        #
        # Pehli koshish mein `assertNotIn("image_b64.encode()[:1000]")`
        # likha tha — aur wo FAIL ho gaya, kyunki us bug ka EXPLANATION
        # usi function ke comment mein likha hai. Comment code nahi hota.
        tree = ast.parse(textwrap.dedent(inspect.getsource(Agent.run_turn)))

        sha_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sha256"
        ]
        self.assertEqual(len(sha_calls), 1, "sha256 call nahi mila")

        argument = sha_calls[0].args[0]
        self.assertNotIsInstance(
            argument, ast.Subscript,
            "sha256 ko SLICE kiya hua data ja raha hai (jaise [:1000]) — "
            "alag screenshot 'same' mana jaayega",
        )

    def test_truncated_hash_sach_mein_collide_karta_hai(self):
        """
        Upar wala test source dekhta hai. Ye SAABIT karta hai ki
        truncation kyun galat thi — do alag string, same truncated hash.
        """
        import hashlib

        a = "X" * 2000 + "screen_pe_paytm"
        b = "X" * 2000 + "screen_pe_youtube"

        truncated_a = hashlib.sha256(a.encode()[:1000]).hexdigest()
        truncated_b = hashlib.sha256(b.encode()[:1000]).hexdigest()
        self.assertEqual(
            truncated_a, truncated_b,
            "1000-byte hash inko same batata hai — yahi bug tha",
        )

        full_a = hashlib.sha256(a.encode()).hexdigest()
        full_b = hashlib.sha256(b.encode()).hexdigest()
        self.assertNotEqual(full_a, full_b, "poora hash inko alag batana chahiye")

    # --- Bug #2: max_screenshots=0 ---

    def test_max_screenshots_zero_pe_image_bilkul_nahi_jaati(self):
        """
        ⚠️ ASLI BUG — `SAARTHI_MAX_SCREENSHOTS=0` pe bhi ek image jaati thi.

        `_evict_old_screenshots()` purane hata deta tha, par uske BAAD
        naya image message append ho jaata tha. Setting ka matlab hi
        khatam — jo log vision-less provider pe hain unke liye ye zaroori
        hai.
        """
        import inspect

        from saarthi.agent import Agent

        source = inspect.getsource(Agent.run_turn)
        self.assertIn(
            "if max_shots <= 0:", source,
            "max_screenshots=0 ka case handle nahi hota — image phir bhi jaayegi",
        )

    # --- Eviction + API contract ---

    def test_evict_tool_result_ko_KABHI_nahi_chhedta(self):
        """
        🚨 API CONTRACT — sabse zaroori.

        Har `tool_call` ka matching `tool_result` hona ZARURI hai. Agar
        eviction usse hata de to LLM API seedha error deta hai
        ("tool_call_id without response") aur poora turn marr jaata hai.

        Evict sirf alag wale `Message.user(image_b64=...)` ko karna hai.
        """
        import ast
        import inspect
        import textwrap

        from saarthi.agent import Agent

        # AST se — docstring mein "tool_result ko KABHI mat chhedna"
        # likha hai, to plain text search galat fail deta hai.
        tree = ast.parse(
            textwrap.dedent(inspect.getsource(Agent._evict_old_screenshots))
        )

        touched = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn(
            "tool_result", touched,
            "eviction tool_result banata/chhedta hai — LLM API "
            "'tool_call_id without response' error dega",
        )

        # Placeholder Message.user() se replace karta hai
        self.assertIn("user", touched, "placeholder message nahi banata")

        # messages list se element POP/DEL nahi hona chahiye — usse
        # baaki saare tracked indices shift ho jaayenge
        for node in ast.walk(tree):
            if isinstance(node, ast.Delete):
                self.fail("messages se `del` kiya ja raha hai — indices tootenge")
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "pop"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "messages"):
                self.fail("self.messages.pop() — indices tootenge, "
                          "placeholder se replace karo")

    def test_evict_placeholder_daalta_hai_chup_chaap_nahi_hatata(self):
        """
        Message ko chup-chaap gayab karna galat hai — LLM ko dikhna
        chahiye ki wahan kuch tha. Warna wo confuse hota hai ki usne
        screenshot maanga tha aur kuch aaya hi nahi.
        """
        import inspect

        from saarthi.agent import Agent

        source = inspect.getsource(Agent._evict_old_screenshots)
        self.assertIn("removed", source.lower())
