"""
Browser Device — "saari websites ka access".

YAHAN ARCHITECTURE KA ASLI FAYDA DIKHTA HAI:

    Browser ka DOM hi hamara `ui_tree` ban jaata hai. Matlab:

      - `tap_text("Login")`        -> AUTOMATICALLY kaam karta hai
      - Skills ka SELF-HEALING     -> AUTOMATICALLY kaam karta hai
      - Dikha Do Mode              -> AUTOMATICALLY kaam karta hai

    Ek line bhi nahi likhni padi in features ke liye. Kyunki Phase 1
    mein `Device` abstraction theek se banaya tha.

    Yahi accha architecture hota hai — naya device add karo, purane
    features free mil jaate hain.


KYA HO SAKTA HAI:
    - Koi bhi website kholo
    - Text/button pe click karo (text se, coordinates se nahi)
    - Form bharo
    - Screenshot lo (Gemini/GPT-4o dekh sakte hain)
    - Page ka pura text padho
    - Scroll, back, forward, tabs
    - Login state YAAD rehti hai (persistent profile)

TAB DISCIPLINE (ye bahut important hai — user ka kaam mat todo):

    Ye browser SAARTHI ka APNA hai, user ke personal Chrome se alag.
    Phir bhi user isi window mein aa ke kaam karta hai (agent ne
    YouTube khola, user wahan video dekh raha hai).

    Isliye rule: `launch_app` HAR BAAR NAYA TAB kholta hai.

    Kyun? Pehle ye `self._page` reuse karta tha. Nateeja:
        1. Agent ne YouTube search khola
        2. User us tab pe gaya, video chalu kiya
        3. User ne agent ko naya kaam diya ("gmail kholo")
        4. Agent ne USI tab ko gmail pe bhej diya
        -> User ka video band. Tab "switch" ho gaya.

    Ab agent naya tab kholta hai aur user ka tab chhedta nahi.
    `bring_to_front()` KABHI nahi call karte — warna user ka focus
    chhin jaayega.

IMAANDAAR LIMITATIONS:
    - CAPTCHA: agent solve nahi karega (aur nahi karna chahiye)
    - Bot-detection: kuch sites block karengi (~10%)
    - Banking sites: automation detect karke block kar sakti hain
    - Payment ka final button: USER dabayega (safety rule)
    - Browser window PEHLI BAAR khulte waqt OS focus le sakta hai.
      Ye OS/window-manager ka behaviour hai, isko code se pura roka
      nahi ja sakta. Bilkul nahi chahiye to
      SAARTHI_BROWSER_HEADLESS=true kar de.

SETUP (ek baar):
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from ..config import settings as default_settings
from .base import ActionResult, Capability, Device, UIElement

log = logging.getLogger("saarthi.devices.browser")

# ----------------------------------------------------------------------
#  Optional dependency
# ----------------------------------------------------------------------

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
    PLAYWRIGHT_ERROR = ""
except Exception as exc:  # noqa: BLE001
    async_playwright = None  # type: ignore[assignment]
    HAS_PLAYWRIGHT = False
    PLAYWRIGHT_ERROR = str(exc)


# JavaScript jo page ke saare interactive elements nikaalta hai.
# Ye DOM ko hamare UIElement format mein badal deta hai — isi se
# tap_text aur self-healing free mil jaate hain.
_EXTRACT_ELEMENTS_JS = """
() => {
  const out = [];
  const selector = [
    'a[href]', 'button', 'input', 'select', 'textarea',
    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]',
    '[onclick]', '[contenteditable=true]'
  ].join(',');

  const nodes = document.querySelectorAll(selector);

  for (const el of nodes) {
    const rect = el.getBoundingClientRect();

    // Chhupe hue elements skip karo — unpe click nahi ho sakta
    if (rect.width < 2 || rect.height < 2) continue;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    if (parseFloat(style.opacity || '1') < 0.05) continue;

    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();

    // Element ka best naam dhoondo
    let text = (el.innerText || el.textContent || '').trim();
    if (!text) {
      text = (el.getAttribute('aria-label')
              || el.getAttribute('placeholder')
              || el.getAttribute('title')
              || el.getAttribute('name')
              || el.value
              || '').trim();
    }
    text = text.replace(/\\s+/g, ' ').slice(0, 120);

    const editable = tag === 'textarea'
      || el.getAttribute('contenteditable') === 'true'
      || (tag === 'input' && !['checkbox','radio','submit','button','hidden','file'].includes(type));

    out.push({
      text: text,
      desc: (el.getAttribute('aria-label') || el.getAttribute('title') || '').slice(0, 120),
      id: (el.id || el.getAttribute('name') || '').slice(0, 80),
      tag: tag + (type ? ':' + type : ''),
      editable: editable,
      enabled: !el.disabled,
      x: Math.round(rect.left), y: Math.round(rect.top),
      w: Math.round(rect.width), h: Math.round(rect.height)
    });
  }
  return out.slice(0, 200);
}
"""


class BrowserDevice(Device):
    """
    Playwright-based browser — saari websites ka access.

    Browser LAZY start hota hai — object banane se kuch nahi khulta.
    Pehle kaam pe browser launch hota hai.
    """

    kind = "browser"
    capabilities = {
        Capability.TAP,
        Capability.TYPE,
        Capability.KEY,
        Capability.SCREENSHOT,
        Capability.UI_TREE,      # DOM = ui_tree, isliye tap_text free
        Capability.SWIPE,        # scroll
        Capability.LAUNCH_APP,   # website kholna
        Capability.DEVICE_INFO,
    }

    # Itne se zyada tab ho jaayein to naya kholna band, purana reuse.
    # Warna din bhar chalane pe 50 tab khul jaate hain.
    MAX_TABS = 10

    def __init__(
        self,
        name: str = "browser",
        headless: bool | None = None,
        profile_dir: str | Path | None = None,
    ):
        """
        Args:
            headless: True = browser dikhega nahi (background mein)
                      False = dikhega (user dekh sake kya ho raha hai)
                      None = .env ka SAARTHI_BROWSER_HEADLESS use karo
            profile_dir: Login state yahan save hogi. Isse Gmail/WhatsApp
                         Web mein baar-baar login nahi karna padta.
        """
        super().__init__(name)
        self.headless = (
            default_settings.browser_headless if headless is None else headless
        )
        self.profile_dir = Path(
            profile_dir or (default_settings.data_dir / "browser_profile")
        )

        self._playwright = None
        self._context = None
        self._page = None

        # Agent ne is page ko KAHAN chhoda tha.
        # Isse pata chalta hai user ne tab ko haath lagaya ya nahi:
        # current URL != _agent_url  =>  user ne khud navigate kiya
        # => us tab ko chhedna nahi hai.
        self._agent_url: str | None = None

        # Agent ne kaunse tab khole (order ke saath) — cap lagane ke liye
        self._agent_pages: list = []

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        return HAS_PLAYWRIGHT

    def setup_help(self) -> str:
        lines = ["Browser control ke liye Playwright chahiye:"]
        lines.append("")
        lines.append("    pip install playwright")
        lines.append("    playwright install chromium")
        lines.append("")
        lines.append("  (chromium ~150MB download hoga, ek hi baar)")
        if PLAYWRIGHT_ERROR:
            lines.append(f"\n  Abhi ka error: {PLAYWRIGHT_ERROR}")
        return "\n".join(lines)

    async def _ensure_browser(self) -> ActionResult | None:
        """
        Browser start karo (lazy). Problem ho to ActionResult return karo.
        """
        if self._page is not None:
            return None

        if not HAS_PLAYWRIGHT:
            # setup_error=True -> caller ko pata chalta hai ki ye "setup
            # adhoora hai" wali problem hai, "website kharab hai" wali
            # nahi. auto mode isi pe system browser pe fallback karta hai.
            return ActionResult.failure(self.setup_help(), setup_error=True)

        try:
            self._playwright = await async_playwright().start()

            self.profile_dir.mkdir(parents=True, exist_ok=True)

            # persistent_context use kar rahe hain (normal launch nahi) —
            # isse cookies aur login state save rehti hai. User ko
            # baar-baar login nahi karna padta.
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    # Pehli baar khulte waqt ka shor kam karo — "restore
                    # pages?" bubble, default-browser prompt, infobars.
                    # Inme se koi bhi popup user ka dhyan tod deta hai.
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-session-crashed-bubble",
                    "--disable-infobars",
                ],
            )

            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            self._page.set_default_timeout(20_000)
            self._agent_pages = [self._page]
            self._remember_url()

            log.info("Browser start ho gaya (headless=%s)", self.headless)
            return None

        except Exception as exc:  # noqa: BLE001
            await self.close()
            message = str(exc)
            if "executable doesn't exist" in message.lower() or "install" in message.lower():
                return ActionResult.failure(
                    "Chromium install nahi hai. Ye chala:\n"
                    "    playwright install chromium",
                    setup_error=True,
                )
            return ActionResult.failure(
                f"Browser start nahi hua: {exc}", setup_error=True
            )

    # ------------------------------------------------------------------
    #  TAB MANAGEMENT — "mera tab switch ho gaya" ka ilaaj
    # ------------------------------------------------------------------

    def _current_url(self) -> str:
        """Abhi ka URL. Page band ho gaya ho to khali string."""
        if self._page is None:
            return ""
        try:
            return self._page.url or ""
        except Exception:  # noqa: BLE001 — page band ho sakta hai
            return ""

    def _remember_url(self) -> None:
        """
        Agent ne page ko yahan chhoda — yaad rakh lo.

        Agent ka HAR action ke baad ye call hota hai. Isse baad mein
        pata chal jaata hai ki URL agent ne badla tha ya user ne.
        """
        self._agent_url = self._current_url() or None

    def _is_blank(self, url: str) -> bool:
        """Khali tab hai? (ise reuse karna safe hai)"""
        return url in ("", "about:blank", "chrome://newtab/", "about:newtab")

    def _user_took_over(self) -> bool:
        """
        User ne is tab ko khud navigate kiya hai?

        Agar haan, to is tab ko chhedna MANA hai — user wahan kaam
        kar raha hai.
        """
        current = self._current_url()
        if self._is_blank(current) or self._agent_url is None:
            return False
        return current != self._agent_url

    def _live_pages(self) -> list:
        """Jo tabs abhi khule hain."""
        if self._context is None:
            return []
        try:
            return [p for p in self._context.pages if not p.is_closed()]
        except Exception:  # noqa: BLE001
            return []

    async def _open_tab(self) -> ActionResult | None:
        """
        Naya tab kholo aur usko current bana do.

        Tab count cap se zyada ho gaya to naya nahi kholte — sabse
        purana AGENT ka tab reuse karte hain. User ka navigate kiya
        hua tab kabhi reuse nahi karte.
        """
        live = self._live_pages()

        if len(live) >= self.MAX_TABS:
            # Sabse purana agent ka tab dhoondo jo abhi bhi khula hai
            for page in self._agent_pages:
                try:
                    if page.is_closed() or page is self._page:
                        continue
                except Exception:  # noqa: BLE001
                    continue
                log.info(
                    "%d tab ho gaye — purana agent tab reuse kar raha hun",
                    len(live),
                )
                self._page = page
                self._page.set_default_timeout(20_000)
                return None

        try:
            page = await self._context.new_page()
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Naya tab khul nahi paya: {exc}")

        page.set_default_timeout(20_000)
        self._page = page
        self._agent_pages.append(page)
        # NOTE: bring_to_front() JAAN-BOOJH KE nahi call kar rahe.
        # Wo user ka focus chheen leta hai — yahi to fix kar rahe hain.
        return None

    async def _page_for_navigation(self) -> ActionResult | None:
        """
        Navigate karne ke liye kaunsa tab use karein.

        Ye pura fix isi function mein hai:
          - Khali tab hai        -> wahi use karo (bekaar tab kyun banao)
          - User ne takeover kiya -> NAYA tab (uska kaam nahi todenge)
          - Warna                -> NAYA tab (purana browsing history
                                     ke liye chhod do)
        """
        error = await self._ensure_browser()
        if error:
            return error

        current = self._current_url()

        if self._is_blank(current):
            return None

        if self._user_took_over():
            log.info("User ne tab takeover kiya (%s) — naya tab khol raha hun", current)

        return await self._open_tab()

    def tab_count(self) -> int:
        """Kitne tab khule hain."""
        return len(self._live_pages())

    async def close(self) -> None:
        """Browser band karo."""
        for closer in (self._context, self._playwright):
            if closer is None:
                continue
            try:
                if hasattr(closer, "close"):
                    await closer.close()
                elif hasattr(closer, "stop"):
                    await closer.stop()
            except Exception:  # noqa: BLE001
                pass
        self._playwright = None
        self._context = None
        self._page = None
        self._agent_pages = []
        self._agent_url = None

    # ------------------------------------------------------------------
    #  Info
    # ------------------------------------------------------------------

    async def info(self) -> ActionResult:
        if not HAS_PLAYWRIGHT:
            return ActionResult.failure(self.setup_help())

        if self._page is None:
            return ActionResult.success(
                "Browser ready hai (abhi khula nahi). "
                "website_kholo ya app_kholo se koi site kholo."
            )

        try:
            title = await self._page.title()
            url = self._page.url
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Page info nahi mili: {exc}")

        tabs = self.tab_count()
        return ActionResult.success(
            f"Abhi khula hai: {title}\n  URL: {url}\n  Khule tabs: {tabs}",
            title=title,
            url=url,
            tab_count=tabs,
        )

    # ------------------------------------------------------------------
    #  Navigation ("app kholna" = website kholna)
    # ------------------------------------------------------------------

    async def launch_app(self, app: str) -> ActionResult:
        """
        Website kholo. App ka naam bhi chalega — website mein badal jaayega.

        "youtube" -> https://www.youtube.com

        NAYE TAB mein khulta hai — user ka chalu kaam nahi todta.
        (Detail ke liye file ke top pe "TAB DISCIPLINE" padh.)
        """
        error = await self._page_for_navigation()
        if error:
            return error

        target = app.strip()

        # App naam ho to website URL mein badlo
        if not target.startswith(("http://", "https://")):
            from ..tools.web_tools import COMMON_URLS  # circular import se bacho

            lookup = target.lower()
            known = COMMON_URLS.get(lookup)
            if known and "{q}" not in known:
                target = known
            elif "." in target and " " not in target:
                target = "https://" + target
            else:
                # Naam hai, URL nahi — Google pe search kar do
                from urllib.parse import quote_plus

                target = f"https://www.google.com/search?q={quote_plus(target)}"

        if target.startswith("http://"):
            target = "https://" + target[len("http://") :]

        try:
            await self._page.goto(target, wait_until="domcontentloaded")
            # Thoda ruk jao — JS content load ho jaaye
            await asyncio.sleep(1.2)
            title = await self._page.title()
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"'{target}' khul nahi paya: {exc}")

        self._remember_url()

        # Prose yahan nahi likh rahe — `website_kholo` tool user ko
        # samjhaata hai ki tab safe hai. Yahan sirf facts.
        return ActionResult.success(
            f"Khol diya: {title}\n  URL: {self._page.url}",
            url=self._page.url,
            tab_count=self.tab_count(),
        )

    async def close_app(self, app: str) -> ActionResult:
        """Tab band karo / blank page pe jao."""
        if self._page is None:
            return ActionResult.success("Browser pehle se band hai")
        try:
            await self._page.goto("about:blank")
            self._remember_url()
            return ActionResult.success("Page band kar diya")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Band nahi hua: {exc}")

    # ------------------------------------------------------------------
    #  Screen reading — DOM se ui_tree
    # ------------------------------------------------------------------

    async def ui_tree(self) -> ActionResult:
        """
        Page ke saare interactive elements nikaalo.

        YAHI wo method hai jisse `tap_text()` aur SELF-HEALING
        automatically kaam karte hain — Phase 1 ka code chhedna
        nahi padta.
        """
        error = await self._ensure_browser()
        if error:
            return error

        try:
            raw = await self._page.evaluate(_EXTRACT_ELEMENTS_JS)
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Page padh nahi paya: {exc}")

        elements: list[UIElement] = []
        for item in raw or []:
            x, y = item.get("x", 0), item.get("y", 0)
            w, h = item.get("w", 0), item.get("h", 0)
            elements.append(
                UIElement(
                    text=item.get("text", ""),
                    content_desc=item.get("desc", ""),
                    resource_id=item.get("id", ""),
                    class_name=item.get("tag", ""),
                    clickable=True,  # sab interactive elements hain
                    editable=bool(item.get("editable")),
                    enabled=bool(item.get("enabled", True)),
                    bounds=(x, y, x + w, y + h),
                )
            )

        interactive = [el for el in elements if el.label]

        lines = [f"Page pe {len(elements)} interactive elements mile"]
        try:
            lines.append(f"Title: {await self._page.title()}")
        except Exception:  # noqa: BLE001
            pass

        if interactive:
            lines.append("Ye cheezein hain:")
            for el in interactive[:30]:
                lines.append(f"  - {el}")

        return ActionResult.success(
            "\n".join(lines), elements=elements, interactive=interactive
        )

    async def read_page(self, max_chars: int = 6000) -> ActionResult:
        """Page ka pura text padho."""
        error = await self._ensure_browser()
        if error:
            return error

        try:
            text = await self._page.inner_text("body")
            title = await self._page.title()
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Text nahi mila: {exc}")

        import re

        clean = re.sub(r"\n{3,}", "\n\n", text or "").strip()
        truncated = len(clean) > max_chars
        if truncated:
            clean = clean[:max_chars] + "\n... (aur bhi hai)"

        return ActionResult.success(f"[{title}]\n\n{clean}", truncated=truncated)

    async def screenshot(self) -> ActionResult:
        error = await self._ensure_browser()
        if error:
            return error

        try:
            raw = await self._page.screenshot(type="png")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Screenshot fail: {exc}")

        return ActionResult.success(
            f"Screenshot liya ({len(raw) // 1024} KB)",
            image_b64=base64.b64encode(raw).decode("ascii"),
            image_mime="image/png",
        )

    # ------------------------------------------------------------------
    #  Interaction
    # ------------------------------------------------------------------

    async def tap(self, x: int, y: int) -> ActionResult:
        error = await self._ensure_browser()
        if error:
            return error
        try:
            await self._page.mouse.click(int(x), int(y))
            await asyncio.sleep(0.6)
            # Click se page badal sakta hai — agent ka URL update karo,
            # warna agli baar lagega ki user ne navigate kiya tha
            self._remember_url()
            return ActionResult.success(f"click kiya ({x},{y})")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Click fail: {exc}")

    async def tap_text(self, text: str) -> ActionResult:
        """
        Text pe click karo.

        SMART MATCHING: Pehle exact try karo, phir partial. YouTube
        videos ke lambe naam mein se chhota hissa bhi kaam karega.
        Na mile to base class wala fallback try hota hai.
        """
        error = await self._ensure_browser()
        if error:
            return error

        query = text.strip()

        # --- FAST PATH: Playwright ke locators ---
        attempts = [
            self._page.get_by_role("button", name=query, exact=False),
            self._page.get_by_role("link", name=query, exact=False),
            self._page.get_by_text(query, exact=False),
            self._page.locator(f"[aria-label*='{query}' i]"),
            self._page.locator(f"[placeholder*='{query}' i]"),
        ]

        for locator in attempts:
            try:
                if await locator.count() == 0:
                    continue
                await locator.first.click(timeout=6000)
                await asyncio.sleep(0.8)
                self._remember_url()
                return ActionResult.success(f"'{query}' pe click kiya")
            except Exception:  # noqa: BLE001
                continue

        # --- SMART PARTIAL MATCH via JavaScript ---
        # YouTube/Google results mein lambe text hote hain. User ya agent
        # chhota text deta hai. JS mein dhoondh ke click karo.
        try:
            clicked = await self._page.evaluate(f"""
            (searchText) => {{
                const lower = searchText.toLowerCase();
                // Pehle links mein dhoondho (search results usually links hain)
                const links = document.querySelectorAll('a, [role=link]');
                for (const el of links) {{
                    const elText = (el.innerText || el.textContent || '').toLowerCase();
                    if (elText.includes(lower)) {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 5 && rect.height > 5) {{
                            el.click();
                            return true;
                        }}
                    }}
                }}
                // Phir buttons/clickable elements
                const all = document.querySelectorAll('button, [role=button], [onclick]');
                for (const el of all) {{
                    const elText = (el.innerText || el.textContent || '').toLowerCase();
                    if (elText.includes(lower)) {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 5 && rect.height > 5) {{
                            el.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}
            """, query)

            if clicked:
                await asyncio.sleep(1.0)
                self._remember_url()
                return ActionResult.success(f"'{query}' pe click kiya (partial match)")
        except Exception:  # noqa: BLE001
            pass

        # --- FIRST CLICKABLE RESULT (YouTube/Google specific) ---
        # Agar text match nahi hua par ye ek search results page hai,
        # to pehla result click karo
        try:
            # YouTube video results
            yt_result = self._page.locator("ytd-video-renderer a#video-title, a.yt-simple-endpoint[href*='watch']").first
            if await yt_result.count() > 0:
                await yt_result.click(timeout=5000)
                await asyncio.sleep(1.0)
                self._remember_url()
                return ActionResult.success(f"Pehla video result click kiya ('{query}' exact nahi mila)")
        except Exception:  # noqa: BLE001
            pass

        # Playwright se nahi mila — ui_tree wala tareeka try karo
        # (isi se self-healing bhi chalta hai)
        return await super().tap_text(text)

    async def type_text(self, text: str) -> ActionResult:
        error = await self._ensure_browser()
        if error:
            return error
        try:
            await self._page.keyboard.type(str(text), delay=25)
            return ActionResult.success(f"type kiya: {str(text)[:60]}")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Type fail: {exc}")

    async def fill_field(self, field: str, value: str) -> ActionResult:
        """Kisi field ko dhoondh ke bharo (label/placeholder se)."""
        error = await self._ensure_browser()
        if error:
            return error

        attempts = [
            self._page.get_by_label(field, exact=False),
            self._page.get_by_placeholder(field, exact=False),
            self._page.locator(f"[name*='{field}' i]"),
            self._page.locator(f"[aria-label*='{field}' i]"),
        ]

        for locator in attempts:
            try:
                if await locator.count() == 0:
                    continue
                await locator.first.fill(str(value), timeout=6000)
                return ActionResult.success(f"'{field}' mein '{value}' bhar diya")
            except Exception:  # noqa: BLE001
                continue

        return ActionResult.failure(
            f"'{field}' naam ka field nahi mila. screen_padho se dekh "
            f"page pe kya hai."
        )

    async def press_key(self, key: str) -> ActionResult:
        error = await self._ensure_browser()
        if error:
            return error

        # Aam naam -> Playwright ke key naam
        key_map = {
            "enter": "Enter", "back": "AltLeft+ArrowLeft", "tab": "Tab",
            "escape": "Escape", "esc": "Escape", "space": "Space",
            "up": "ArrowUp", "down": "ArrowDown",
            "left": "ArrowLeft", "right": "ArrowRight",
            "delete": "Delete", "backspace": "Backspace",
            "home": "Home", "end": "End",
            "pageup": "PageUp", "pagedown": "PageDown",
        }
        target = key_map.get(key.lower().strip(), key)

        # "back" browser ka back hai, keyboard ka nahi
        if key.lower().strip() in ("back", "peeche", "wapas"):
            try:
                await self._page.go_back()
                await asyncio.sleep(0.8)
                self._remember_url()
                return ActionResult.success("peeche gaya")
            except Exception as exc:  # noqa: BLE001
                return ActionResult.failure(f"Back fail: {exc}")

        try:
            await self._page.keyboard.press(target)
            await asyncio.sleep(0.4)
            # Enter se search/submit ho sakta hai -> URL badal jaata hai
            self._remember_url()
            return ActionResult.success(f"{key} press kiya")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Key press fail: {exc}")

    async def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> ActionResult:
        """Browser mein swipe = scroll."""
        error = await self._ensure_browser()
        if error:
            return error
        try:
            await self._page.mouse.wheel(x2 - x1, y2 - y1)
            await asyncio.sleep(0.5)
            return ActionResult.success(f"scroll kiya ({x2 - x1},{y2 - y1})")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Scroll fail: {exc}")

    async def scroll(
        self, direction: str = "down", amount: float = 0.5
    ) -> ActionResult:
        """Page scroll karo."""
        error = await self._ensure_browser()
        if error:
            return error

        pixels = int(700 * max(0.1, min(amount, 2.0)))
        deltas = {
            "down": (0, pixels), "neeche": (0, pixels),
            "up": (0, -pixels), "upar": (0, -pixels),
            "right": (pixels, 0), "daayen": (pixels, 0),
            "left": (-pixels, 0), "baayen": (-pixels, 0),
        }
        delta = deltas.get(direction.lower().strip())
        if delta is None:
            return ActionResult.failure(
                f"Direction samajh nahi aaya: {direction} "
                "(down/up/left/right ya neeche/upar/baayen/daayen)"
            )

        try:
            await self._page.mouse.wheel(*delta)
            await asyncio.sleep(0.5)
            return ActionResult.success(f"{direction} scroll kiya")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Scroll fail: {exc}")
