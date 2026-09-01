"""
Browser tab safety + URL resolution.

Ye tests PLAYWRIGHT KE BINA chalte hain — tab logic pure state machine
hai (hardware/browser se alag), bilkul waise hi jaise SilenceDetector
bina mic ke test hota hai. Architecture rule: "hardware logic se alag".
"""

from __future__ import annotations

import asyncio

from tests.helpers import FakePage, SaarthiTestCase, clean_env

from saarthi.brain.types import ToolCall
from saarthi.config import Settings
from saarthi.devices import DeviceManager
from saarthi.devices.browser import BrowserDevice
from saarthi.tools import default_registry
from saarthi.tools.base import ToolContext
from saarthi.tools.web_tools import COMMON_URLS, resolve_target


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class UrlResolution(SaarthiTestCase):
    """
    `website_kholo` ek hi call mein kaam kare — do step na le.

    Pehle LLM ko poora URL banana padta tha, ya wo 5 step leta tha
    (site kholo -> screen padho -> search box dhoondho -> type -> Enter).
    """

    def test_naam_plus_search_ek_call_mein_ban_jaata_hai(self):
        cases = [
            (("youtube", "tum hi ho"),
             "https://www.youtube.com/results?search_query=tum+hi+ho&sp=EgIQAQ%3D%3D"),
            (("youtube", "tere bin"),
             "https://www.youtube.com/results?search_query=tere+bin&sp=EgIQAQ%3D%3D"),
            (("flipkart", "shoes"), "https://www.flipkart.com/search?q=shoes"),
            (("maps", "connaught place"),
             "https://maps.google.com/?q=connaught+place"),
        ]
        for (name, query), expected in cases:
            self.assertEqual(resolve_target(name, query), expected, f"toota: {name}")

    def test_sirf_naam_dene_pe_home_page(self):
        self.assertEqual(resolve_target("youtube"), "https://www.youtube.com")
        self.assertEqual(resolve_target("irctc"), "https://www.irctc.co.in")

    def test_poora_url_bhi_chalta_hai(self):
        self.assertEqual(
            resolve_target("https://web.whatsapp.com"), "https://web.whatsapp.com"
        )

    def test_http_https_ban_jaata_hai(self):
        """Security: kabhi plain http pe nahi jaana."""
        self.assertEqual(resolve_target("http://example.com"), "https://example.com")

    def test_domain_pehchaan_leta_hai(self):
        self.assertEqual(resolve_target("youtube.com"), "https://youtube.com")

    def test_anjaan_naam_google_search_ban_jaata_hai(self):
        """Haar mat maano — "URL galat hai" bolke rukna sabse bura hai."""
        result = resolve_target("koi random cheez")
        self.assertTrue(result.startswith("https://www.google.com/search?q="))

    def test_khali_input_pe_khali_result(self):
        self.assertEqual(resolve_target(""), "")

    def test_common_urls_ka_shape_nahi_toota(self):
        """browser.py isi dict ko import karta hai — shape badla to toot jaayega."""
        for key, value in COMMON_URLS.items():
            self.assertEqual(key, key.lower(), f"'{key}' lowercase nahi hai")
            self.assertTrue(value.startswith("https://"), f"'{key}' https nahi hai")


class TabSafety(SaarthiTestCase):
    """
    User ka tab kabhi hijack nahi hona chahiye.

    Asli scenario jo toota tha:
      1. Agent ne YouTube search khola
      2. User us tab pe gaya, video chalu kiya
      3. Agent ko naya kaam mila
      4. Agent ne USI tab ko doosri site pe bhej diya -> video band
    """

    def test_khali_tab_pehchaan_leta_hai(self):
        device = BrowserDevice()
        for blank in ("", "about:blank", "chrome://newtab/", "about:newtab"):
            self.assertTrue(device._is_blank(blank), f"{blank!r}")

    def test_asli_page_khali_nahi_hai(self):
        device = BrowserDevice()
        for url in ("https://youtube.com", "https://example.com/page"):
            self.assertFalse(device._is_blank(url), url)

    def test_agent_ne_chhoda_wahi_url_hai_to_takeover_nahi(self):
        device = BrowserDevice()
        device._page = FakePage("https://youtube.com/results?q=x")
        device._agent_url = "https://youtube.com/results?q=x"
        self.assertFalse(device._user_took_over())

    def test_user_ne_navigate_kiya_to_takeover_detect_hota_hai(self):
        device = BrowserDevice()
        device._page = FakePage("https://youtube.com/results?q=x")
        device._agent_url = "https://youtube.com/results?q=x"
        # User ne video pe click kiya — URL badal gaya, agent ko pata nahi
        device._page = FakePage("https://youtube.com/watch?v=abc")
        self.assertTrue(
            device._user_took_over(),
            "Takeover detect nahi hua — agent user ka tab chheen lega",
        )

    def test_agent_url_pata_na_ho_to_takeover_nahi_maanta(self):
        """Fresh start pe takeover maanna galat hoga."""
        device = BrowserDevice()
        device._page = FakePage("https://youtube.com")
        device._agent_url = None
        self.assertFalse(device._user_took_over())

    def test_blank_page_pe_takeover_nahi_maanta(self):
        device = BrowserDevice()
        device._page = FakePage("about:blank")
        device._agent_url = "https://youtube.com"
        self.assertFalse(device._user_took_over())

    def test_max_tabs_cap_hai(self):
        """Din bhar chalane pe 50 tab nahi khulne chahiye."""
        self.assertEqual(BrowserDevice.MAX_TABS, 10)

    def test_headless_explicit_pass_kar_sakte_hain(self):
        self.assertTrue(BrowserDevice(headless=True).headless)
        self.assertFalse(BrowserDevice(headless=False).headless)

    def test_headless_none_dene_pe_settings_se_aata_hai(self):
        from saarthi.config import settings as live_settings

        device = BrowserDevice(headless=None)
        self.assertEqual(device.headless, live_settings.browser_headless)

    def test_bring_to_front_kabhi_call_nahi_hota(self):
        """Wahi focus chheenta hai — yahi to fix kar rahe the."""
        import inspect

        import saarthi.devices.browser as module

        for line in inspect.getsource(module).splitlines():
            stripped = line.strip()
            if ".bring_to_front(" in stripped and not stripped.startswith("#"):
                self.fail(f"bring_to_front() call mila: {stripped}")


class BrowserModeRouting(SaarthiTestCase):
    """
    `website_kholo` teen mode mein kaam karta hai.

    Khaas: 'agent' mode set ho aur agent ka browser na ho to CHUP-CHAAP
    user ke personal browser pe fallback NAHI karna — wahi to bachana
    tha.
    """

    def make_ctx(self, mode):
        with clean_env(GROQ_API_KEY="fake"):
            settings = Settings.load()
        settings.browser_mode = mode
        manager = DeviceManager(settings)
        manager.setup_defaults()
        return ToolContext(devices=manager, settings=settings)

    def call(self, mode, url="youtube", search="tere bin"):
        return run(
            default_registry().execute(
                ToolCall(id="t", name="website_kholo",
                         arguments={"url": url, "search": search}),
                self.make_ctx(mode),
            )
        )

    def patched_webbrowser(self):
        """webbrowser.open pakad lo — asli browser nahi kholna."""
        import webbrowser

        opened = []
        original = webbrowser.open

        def fake_open(url, new=0, autoraise=True):
            opened.append({"url": url, "new": new, "autoraise": autoraise})
            return True

        webbrowser.open = fake_open
        return opened, (lambda: setattr(webbrowser, "open", original))

    def test_system_mode_naye_tab_mein_kholta_hai(self):
        opened, restore = self.patched_webbrowser()
        try:
            result = self.call("system")
        finally:
            restore()

        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["new"], 2, "new=2 nahi — current tab replace hoga")
        self.assertIs(opened[0]["autoraise"], False, "autoraise=False nahi — focus chheenega")
        self.assertEqual(
            opened[0]["url"],
            "https://www.youtube.com/results?search_query=tere+bin&sp=EgIQAQ%3D%3D",
        )

    def no_playwright(self):
        """
        Playwright ko "installed nahi hai" bana do.

        Ye zaroori hai warna test ASLI chromium launch kar dega —
        dheema, network chahiye, aur CI pe fail hoga.
        """
        import saarthi.devices.browser as module

        original = module.HAS_PLAYWRIGHT
        module.HAS_PLAYWRIGHT = False
        return lambda: setattr(module, "HAS_PLAYWRIGHT", original)

    def test_agent_mode_browser_na_ho_to_saaf_fail_hota_hai(self):
        restore_pw = self.no_playwright()
        opened, restore_wb = self.patched_webbrowser()
        try:
            result = self.call("agent")
        finally:
            restore_wb()
            restore_pw()

        self.assertFalse(result.ok, "agent browser nahi tha par kaam ho gaya?")
        self.assertEqual(
            len(opened), 0,
            "agent mode tha par user ke personal browser pe fallback kar diya!",
        )
        self.assertIn("playwright", (result.error or "").lower())
        self.assertIn("SAARTHI_BROWSER_MODE=system", result.error or "")

    def test_auto_mode_setup_na_ho_to_system_pe_fallback_karta_hai(self):
        """
        'auto' mode forgiving hai — user ka kaam hona zyada important
        hai (prompt rule: haar mat maano).
        """
        restore_pw = self.no_playwright()
        opened, restore_wb = self.patched_webbrowser()
        try:
            result = self.call("auto")
        finally:
            restore_wb()
            restore_pw()

        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(opened), 1, "system browser pe fallback nahi hua")
        self.assertEqual(opened[0]["new"], 2)
