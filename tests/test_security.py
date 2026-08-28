"""
Security layer — redaction + banking lockdown.

⚠️ YE FILE EK ASLI GAP SE BANI HAI.

User ne poocha: "mera agent bank ka access na le, UPI payment na kar
sake, card details read na kare — aisa hai na?"

Jawab NAHI tha. Scan mein ye mila:

  1. `safety.py` sirf TYPE karne pe rok lagata tha (OTP/PIN/CVV/password).
     PADHNE pe koi rok nahi thi.

  2. `screen_padho` screen ka saara text LLM ko bhejta tha — aur LLM
     cloud pe hai (NVIDIA/Groq/Gemini). Card number, balance, transaction
     history — sab third-party server pe.

  3. `read_notifications()` `dumpsys notification --noredact` chalata tha.
     `--noredact` = "Android, sensitive content chhupao MAT". Matlab OTP
     ka notification padh ke cloud LLM ko bheja ja sakta tha — jabki
     `safety.py` mein "OTP type nahi karunga" ka hard block hai. Seedha
     contradiction.

  4. Koi app blocklist nahi thi — agent Paytm/PhonePe/ICICI sab khol
     sakta tha.
"""

from __future__ import annotations

from tests.helpers import SaarthiTestCase, clean_env


# ----------------------------------------------------------------------
#  REDACTION
# ----------------------------------------------------------------------


class Redaction(SaarthiTestCase):
    """Card/OTP/CVV/account LLM tak na pahunche."""

    def redact(self, text):
        from saarthi.tools.redact import redact_sensitive

        return redact_sensitive(text)

    # --- Jo HATNA chahiye ---

    def test_card_number_hat_jaata_hai(self):
        clean, found = self.redact("Card 4111 1111 1111 1111 expiry 12/26")
        self.assertNotIn("4111 1111 1111 1111", clean)
        self.assertIn("card number", found)

    def test_card_ke_aakhri_4_digit_bache_rehte_hain(self):
        """
        User ko pehchaan aani chahiye kaunsa card tha. Poora hata dene se
        agent bhi confuse hota hai aur user bhi.
        """
        clean, _ = self.redact("4111111111111111")
        self.assertIn("1111", clean)
        self.assertNotIn("4111111111111111", clean)

    def test_bina_space_wala_card_bhi_pakadta_hai(self):
        clean, found = self.redact("card:5500000000000004 done")
        self.assertIn("card number", found)
        self.assertNotIn("5500000000000004", clean)

    def test_otp_context_ke_saath_hat_jaata_hai(self):
        for text in (
            "Your OTP is 483920. Do not share.",
            "OTP: 112233",
            "verification code 8821",
            "One Time Password 445566 valid for 10 min",
        ):
            with self.subTest(text=text):
                clean, found = self.redact(text)
                self.assertIn("OTP", found, f"{text!r} se OTP nahi hata")

    def test_cvv_hat_jaata_hai(self):
        clean, found = self.redact("CVV: 123")
        self.assertIn("CVV", found)
        self.assertNotIn("123", clean)

    def test_account_number_hat_jaata_hai(self):
        clean, found = self.redact("A/c no 123456789012 balance Rs 5420")
        self.assertIn("account number", found)
        self.assertNotIn("123456789012", clean)

    def test_ifsc_hat_jaata_hai(self):
        clean, found = self.redact("IFSC HDFC0001234")
        self.assertIn("IFSC", found)
        self.assertNotIn("HDFC0001234", clean)

    # --- ⚠️ Jo NAHI hatna chahiye (false positive = agent confuse) ---

    def test_normal_text_chhedta_NAHI(self):
        """
        Ye test us galti se bachata hai jo is feature ko ULTA kar deti.

        Agar redaction aggressive ho jaaye to agent ko har jagah
        `[REDACTED]` dikhega, wo screen samajh hi nahi paayega, aur
        poora agent bekaar ho jaayega. False positive ka nuksaan asli
        hai.
        """
        safe = [
            "paytm kholo",
            "2500 rupay bhej do",
            "Mera number 9876543210 hai",
            "Pincode 110045",
            "Balance Rs 5420",
            "Order ID 1234567890123456 delivered",   # Luhn fail
            "IMEI 490154203237518",
            "Send Money",
            "bijli ka bill bhar do",
            "12/26",
            "Total 1,24,500",
        ]
        for text in safe:
            with self.subTest(text=text):
                clean, found = self.redact(text)
                self.assertEqual(
                    found, [],
                    f"{text!r} se galti se {found} hata diya — agent confuse hoga",
                )
                self.assertEqual(clean, text)

    def test_luhn_fail_karne_wala_number_card_nahi_mana_jaata(self):
        """
        16-digit number = card number maan lena GALAT hai. Order ID,
        tracking number, IMEI sab 13-19 digit ke hote hain.

        Isliye Luhn checksum use karte hain — asli card numbers wo pass
        karte hain, random numbers nahi.
        """
        from saarthi.tools.redact import _luhn_ok

        self.assertTrue(_luhn_ok("4111111111111111"), "asli card Luhn pass kare")
        self.assertTrue(_luhn_ok("5500000000000004"))
        self.assertFalse(_luhn_ok("1234567890123456"), "random number Luhn fail kare")
        self.assertFalse(_luhn_ok("1111111111111111"))

    def test_akela_6_digit_number_OTP_nahi_mana_jaata(self):
        """
        Context ke bina 6-digit redact karna galat hai — pincode, amount,
        year, quantity sab 4-6 digit ke hote hain.
        """
        clean, found = self.redact("Total 483920 items in stock")
        self.assertEqual(found, [], "context ke bina OTP maan liya")

    # --- Switch aur crash-safety ---

    def test_redaction_DEFAULT_ON_hai(self):
        """
        Ye feature nahi, BUG FIX hai. Card number third-party API pe
        bhejna kisi bhi mode mein theek nahi. Default ON hona chahiye.
        """
        from saarthi.tools.redact import redaction_enabled

        with clean_env():
            self.assertTrue(redaction_enabled(), "redaction default OFF hai")

    def test_env_se_band_ho_sakti_hai(self):
        from saarthi.tools.redact import redaction_enabled

        with clean_env(SAARTHI_REDACT_SENSITIVE="false"):
            self.assertFalse(redaction_enabled())

    def test_None_aur_non_str_pe_crash_NAHI(self):
        """
        Redaction khud ek outage nahi banni chahiye. Type ki wajah se
        crash hui to poora agent ruk jaayega. (Ye BUG#2 ka sabak hai.)
        """
        for value in (None, 1234, 12.5, [], {}):
            with self.subTest(value=value):
                clean, found = self.redact(value)
                self.assertIsInstance(clean, str)
                self.assertIsInstance(found, list)

    def test_redaction_note_LLM_ko_batata_hai(self):
        """
        Chup-chaap hatana galat hai — agent ko lagega text waisa hi tha
        aur wo galat conclusion nikaalega.
        """
        from saarthi.tools.redact import redaction_note

        note = redaction_note(["card number"])
        self.assertIn("card number", note)
        self.assertIn("SECURITY", note)
        self.assertEqual(redaction_note([]), "", "kuch na mile to note nahi")


# ----------------------------------------------------------------------
#  BANKING LOCK
# ----------------------------------------------------------------------


class BankingLock(SaarthiTestCase):
    """Agent ko paise wale apps se door rakhne ka switch."""

    def test_lock_DEFAULT_OFF_hai(self):
        """
        ON karne se "paytm kholo" aur "bijli ka bill bhar do" band ho
        jaate hain — ye core use cases hain. Isliye user ka faisla.
        """
        from saarthi.tools.banking import banking_locked

        with clean_env():
            self.assertFalse(banking_locked(), "banking lock default ON hai")

    def test_lock_ON_pe_banking_app_block_hota_hai(self):
        from saarthi.tools.banking import check_app_allowed

        with clean_env(SAARTHI_BANKING_LOCK="true"):
            for app in ("paytm", "phonepe", "gpay", "icici", "sbi", "kotak"):
                with self.subTest(app=app):
                    allowed, reason = check_app_allowed(app)
                    self.assertFalse(allowed, f"{app} lock ON hone pe bhi allowed")
                    self.assertIn("BANKING LOCK", reason)

    def test_block_hone_pe_wajah_ACTIONABLE_hoti_hai(self):
        """
        Sirf "blocked" likhna bekaar hai. User ko pata hona chahiye
        kaise badle — warna wo samjhega agent tuta hua hai.
        """
        from saarthi.tools.banking import check_app_allowed

        with clean_env(SAARTHI_BANKING_LOCK="true"):
            _, reason = check_app_allowed("paytm")
        self.assertIn("SAARTHI_BANKING_LOCK=false", reason)

    def test_lock_ON_pe_bhi_normal_app_khulta_hai(self):
        from saarthi.tools.banking import check_app_allowed

        with clean_env(SAARTHI_BANKING_LOCK="true"):
            for app in ("youtube", "whatsapp", "chrome", "swiggy", "irctc"):
                with self.subTest(app=app):
                    self.assertTrue(check_app_allowed(app)[0])

    def test_lock_OFF_pe_kuch_nahi_badalta(self):
        """Regression — default behaviour bilkul same rehna chahiye."""
        from saarthi.tools.banking import check_app_allowed

        with clean_env():
            for app in ("paytm", "phonepe", "youtube"):
                with self.subTest(app=app):
                    self.assertTrue(check_app_allowed(app)[0])

    # --- Matching precision (BUG#1 ka class) ---

    def test_package_name_pe_FAIL_CLOSED_hai(self):
        """
        Package names pe SUBSTRING match karte hain, jaan-boojh ke.

        "com.icicibank.imobile" mein "bank" alag shabd nahi hai —
        "icicibank" ek token hai. Word boundary se ye MISS ho jaata aur
        agent bank app khol deta chahe lock ON ho.

        Security control fail-CLOSED hona chahiye:
          false positive = ek app nahi khulega (irritating, SAFE)
          false negative = bank app khul jaayega (SECURITY FAIL)
        """
        from saarthi.tools.banking import is_banking_app

        for package in (
            "com.icicibank.imobile",
            "com.axisbank.mobile",
            "net.one97.paytm",
            "in.org.npci.upiapp",
            "com.phonepe.app",
        ):
            with self.subTest(package=package):
                self.assertTrue(is_banking_app(package), f"{package} miss ho gaya")

    def test_friendly_naam_pe_WORD_BOUNDARY_hai(self):
        """
        ⚠️ BUG#1 KA CLASS — substring matching.

        BUG#1 mein "paytm" ke andar ka "pay" match ho gaya tha aur
        "wahi" mein "wa" se WhatsApp. Yahan wahi khatra hai: "sbi"
        "sbi_diary" mein hai, "upi" "myupiwala" mein.

        Bina boundary ke ye layer galat apps block karegi aur user ka
        bharosa jaayega.
        """
        from saarthi.tools.banking import is_banking_app

        for text in ("paytmnotes", "sbi_diary", "myupiwala", "upiwala",
                     "youtube", "whatsapp", "chrome"):
            with self.subTest(text=text):
                self.assertFalse(
                    is_banking_app(text),
                    f"'{text}' banking app nahi hai par block ho gaya",
                )

    def test_normal_package_block_nahi_hota(self):
        from saarthi.tools.banking import is_banking_app

        for package in ("com.google.android.youtube", "com.android.chrome",
                        "com.whatsapp", "in.swiggy.android"):
            with self.subTest(package=package):
                self.assertFalse(is_banking_app(package))

    def test_None_aur_khali_pe_crash_NAHI(self):
        from saarthi.tools.banking import check_app_allowed, is_banking_app

        for value in (None, "", "   ", 123):
            with self.subTest(value=value):
                self.assertIsInstance(is_banking_app(value), bool)
                allowed, _ = check_app_allowed(value)
                self.assertIsInstance(allowed, bool)

    # --- User ka apna blocklist ---

    def test_blocked_apps_env_se_kaam_karta_hai(self):
        from saarthi.tools.banking import check_app_allowed

        with clean_env(SAARTHI_BLOCKED_APPS="tinder,gallery"):
            self.assertFalse(check_app_allowed("tinder")[0])
            self.assertFalse(check_app_allowed("gallery")[0])
            self.assertTrue(check_app_allowed("youtube")[0])

    def test_blocked_apps_banking_lock_se_ALAG_chalta_hai(self):
        """Blocked apps hamesha lagta hai, lock OFF ho to bhi."""
        from saarthi.tools.banking import check_app_allowed

        with clean_env(SAARTHI_BLOCKED_APPS="tinder"):
            self.assertFalse(check_app_allowed("tinder")[0])

    # --- Screenshot ---

    def test_lock_ON_pe_banking_screen_ka_screenshot_block(self):
        """
        Screenshot pe khaas rok: redaction TEXT pe lagti hai, IMAGE pe
        nahi. Screenshot mein card/balance saaf dikhta hai aur wo seedha
        vision model ko jaata hai.
        """
        from saarthi.tools.banking import screenshot_allowed

        with clean_env(SAARTHI_BANKING_LOCK="true"):
            allowed, reason = screenshot_allowed("net.one97.paytm")
            self.assertFalse(allowed)
            self.assertIn("screen_padho", reason, "alternative suggest nahi karta")

            self.assertTrue(screenshot_allowed("com.android.chrome")[0])

    def test_current_app_pata_na_chale_to_ALLOW(self):
        """
        Ye tradeoff DOCUMENTED hai, chhupa nahi.

        Block karne se banking lock ON karte hi saare screenshot band ho
        jaate (browser, desktop bhi) aur agent bekaar ho jaata.
        """
        from saarthi.tools.banking import screenshot_allowed

        with clean_env(SAARTHI_BANKING_LOCK="true"):
            self.assertTrue(screenshot_allowed("")[0])
            self.assertTrue(screenshot_allowed(None)[0])

    def test_lock_OFF_pe_screenshot_hamesha_allowed(self):
        from saarthi.tools.banking import screenshot_allowed

        with clean_env():
            self.assertTrue(screenshot_allowed("net.one97.paytm")[0])


# ----------------------------------------------------------------------
#  WIRING — layer bani par tool use na kare to bekaar hai (BUG#11 class)
# ----------------------------------------------------------------------


class SecurityWiring(SaarthiTestCase):
    """
    Redaction/lock ka code sahi ho par tool usse call na kare to poori
    mehnat bekaar. BUG#11 exactly yahi tha — setting `.env` mein thi,
    code mein use hi nahi hoti thi.
    """

    def tool_source(self, name: str) -> str:
        import inspect

        from saarthi.tools import default_registry

        tool = default_registry().get(name)
        self.assertIsNotNone(tool, f"tool '{name}' registry mein nahi mila")
        return inspect.getsource(type(tool).run)

    # ------------------------------------------------------------------
    #  BEHAVIOUR tests — source-inspection se BEHTAR
    #
    #  ⚠️ Pehle ye teen test sirf `assertIn("redact_sensitive", source)`
    #  karte the. Maine verify karne ke liye redaction ka code path DEAD
    #  kar diya (`result = await ...` ko `return await ...` banaya) — aur
    #  TEENO TEST PASS HO GAYE, kyunki shabd source mein bacha hua tha
    #  jabki wo line chalti hi nahi thi.
    #
    #  Isliye ab asli tool CHALATE hain fake device ke saath aur output
    #  check karte hain. Ye chauthi baar hai jab is project mein
    #  source-inspection test ne dhoka diya.
    # ------------------------------------------------------------------

    def run_tool(self, name: str, fake_device, **kwargs):
        """Tool ko asli mein chalao, ek fake device ke saath."""
        import asyncio

        from saarthi.config import Settings
        from saarthi.tools import default_registry
        from saarthi.tools.base import ToolContext

        class FakeManager:
            devices = {"phone": fake_device}

            def get(self, name=None):
                return fake_device

        tool = default_registry().get(name)
        with clean_env():
            ctx = ToolContext(devices=FakeManager(), settings=Settings.load())
            return asyncio.run(tool.run(ctx, **kwargs))

    def test_screen_padho_ka_OUTPUT_redact_hota_hai(self):
        from saarthi.devices.base import ActionResult, Capability

        card = "4111 1111 1111 1111"

        class FakeDevice:
            name = "phone"
            kind = "android"

            def can(self, capability):
                return True

            async def ui_tree(self):
                return ActionResult.success(f'"Card {card}" at (100,200)')

        result = self.run_tool("screen_padho", FakeDevice())

        self.assertNotIn(
            card, result.output,
            "card number LLM ko ja raha hai — redaction ka code path dead hai",
        )
        self.assertIn("REDACTED", result.output)

    def test_notifications_padho_ka_OUTPUT_redact_hota_hai(self):
        """Notifications mein OTP aata hai — sabse zaroori jagah."""
        from saarthi.devices.base import ActionResult

        class FakeDevice:
            name = "phone"
            kind = "android"

            def can(self, capability):
                return True

            async def read_notifications(self):
                return ActionResult.success("SMS: Your OTP is 483920 for login")

        result = self.run_tool("notifications_padho", FakeDevice())

        self.assertNotIn("483920", result.output, "OTP LLM ko ja raha hai")
        self.assertIn("REDACTED", result.output)

    def test_page_padho_ka_OUTPUT_redact_hota_hai(self):
        """Banking WEBSITE bhi utni khatarnak hai jitni app."""
        from saarthi.devices.base import ActionResult

        class FakeDevice:
            name = "browser"
            kind = "browser"

            def can(self, capability):
                return True

            async def read_page(self, max_chars=6000):
                return ActionResult.success("A/c no 123456789012 Bal 5420")

        result = self.run_tool("page_padho", FakeDevice())

        self.assertNotIn("123456789012", result.output)
        self.assertIn("REDACTED", result.output)

    def test_saaf_output_pe_note_nahi_lagta(self):
        """
        Kuch sensitive na ho to output bilkul waisa hi rehna chahiye —
        bekaar ka `[SECURITY: ...]` note nahi lagna chahiye.
        """
        from saarthi.devices.base import ActionResult

        class FakeDevice:
            name = "phone"
            kind = "android"

            def can(self, capability):
                return True

            async def ui_tree(self):
                return ActionResult.success('"Send Money" at (100,200)')

        result = self.run_tool("screen_padho", FakeDevice())
        self.assertEqual(result.output, '"Send Money" at (100,200)')

    def test_app_kholo_lock_check_karta_hai(self):
        source = self.tool_source("app_kholo")
        self.assertIn("check_app_allowed", source)

    def test_app_kholo_ka_check_SABSE_PEHLE_hai(self):
        """
        Security check device resolve se PEHLE hona chahiye. Baad mein ho
        to koi naya code path usse bypass kar sakta hai.
        """
        source = self.tool_source("app_kholo")
        check_at = source.index("check_app_allowed")
        resolve_at = source.index("_resolve_device")
        self.assertLess(
            check_at, resolve_at,
            "security check device resolve ke BAAD hai — bypass ho sakta hai",
        )

    def test_screenshot_lo_lock_check_karta_hai(self):
        source = self.tool_source("screenshot_lo")
        self.assertIn("screenshot_allowed", source)

    def test_noredact_flag_HATA_diya_gaya_hai(self):
        """
        🚨 ASLI BUG — `dumpsys notification --noredact`

        `--noredact` = "Android, sensitive content chhupao MAT". Android
        by default OTP notifications redact karta hai; wo flag usse
        bypass kar raha tha. Matlab OTP padh ke cloud LLM ko bheja ja
        sakta tha — jabki safety.py mein "OTP type nahi karunga" ka hard
        block hai. Seedha contradiction.

        ⚠️ AST SE CHECK KARTE HAIN, TEXT SE NAHI.

        Pehli koshish mein plain text search kiya tha aur wo GALAT FAIL
        hua — kyunki us bug ka EXPLANATION usi function ke DOCSTRING
        mein likha hai (jisme `--noredact` shabd hai). Comment aur
        docstring code nahi hote.

        Ye galti is project mein TEESRI baar hui hai (BUG#22 aur Phase 3
        ke tests mein bhi). Isliye rule: source-inspection test AST se.
        """
        import ast
        import inspect
        import textwrap

        from saarthi.devices.android import AndroidDevice

        tree = ast.parse(
            textwrap.dedent(inspect.getsource(AndroidDevice.read_notifications))
        )

        # `self._shell(...)` ko diye gaye ASLI string arguments nikaalo.
        # Docstring isse bahar reh jaati hai kyunki wo kisi call ka
        # argument nahi hai.
        commands: list[str] = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_shell"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        commands.append(arg.value)

        self.assertTrue(commands, "_shell() ko koi command string nahi ja rahi")

        joined = " ".join(commands)
        self.assertIn("dumpsys notification", joined, "command badal gayi hai")
        self.assertNotIn(
            "--noredact", joined,
            "--noredact wapas aa gaya — Android ki apni OTP redaction "
            "bypass ho jaayegi aur OTP cloud LLM ko ja sakta hai",
        )
