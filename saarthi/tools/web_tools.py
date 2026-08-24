"""
Web Tools — internet ka access.

Ye tera "har cheez ka knowledge" wala hissa hai.

Sab FREE hai:
  - DuckDuckGo search: koi API key nahi chahiye
  - Page fetch: seedha HTTP

Aage Playwright add karenge to login wali websites bhi chalengi
(Phase 3 — "saari websites ka access").
"""

from __future__ import annotations

import asyncio
import re

import httpx

from ..devices.base import ActionResult
from .base import Tool, ToolContext

# Normal browser jaisa dikhna zaroori hai, warna kai sites block karti hain
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _html_to_text(html: str, max_chars: int = 6000) -> str:
    """
    HTML se saaf text nikaalo.

    BeautifulSoup ho to wo use karo, warna regex se kaam chala lo.
    Dependency optional rakhi hai taaki setup aasaan rahe.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Bekaar tags hatao
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]
        ):
            tag.decompose()

        text = soup.get_text(separator="\n")

    except ImportError:
        # Fallback — bs4 nahi hai
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;?", " ", text)
        text = re.sub(r"&amp;?", "&", text)

    # Khali lines saaf karo
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + f"\n\n... (aur {len(cleaned) - max_chars} characters)"

    return cleaned.strip()


class WebSearchTool(Tool):
    name = "internet_pe_dhoondho"
    description = (
        "Internet pe search karo. Tab use kar jab koi current information "
        "chahiye — news, prices, latest info, ya kuch bhi jo tujhe nahi pata. "
        "Free hai, koi API key nahi chahiye."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Kya search karna hai",
            },
            "count": {
                "type": "integer",
                "description": "Kitne results (default 5, max 10)",
            },
        },
        "required": ["query"],
    }

    async def run(
        self, ctx: ToolContext, query: str, count: int = 5
    ) -> ActionResult:
        count = max(1, min(int(count), 10))

        # Library ka naam badal gaya hai: duckduckgo-search -> ddgs.
        # Dono support karte hain taaki purana setup bhi chalta rahe.
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # type: ignore[no-redef]
            except ImportError:
                return ActionResult.failure(
                    "Search library nahi hai. Install kar: pip install ddgs"
                )

        def _search() -> list[dict]:
            # DDGS sync hai — thread mein chalayenge
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=count))

        try:
            # Sync library ko async loop block karne se bachao
            results = await asyncio.wait_for(
                asyncio.to_thread(_search), timeout=30.0
            )
        except asyncio.TimeoutError:
            return ActionResult.failure("Search timeout ho gaya")
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Search fail: {exc}")

        if not results:
            return ActionResult.success(
                f"'{query}' ke liye kuch nahi mila. Query badal ke try kar."
            )

        lines = [f"'{query}' ke {len(results)} results:", ""]
        for i, item in enumerate(results, 1):
            title = item.get("title", "(no title)")
            body = (item.get("body") or "").strip()
            url = item.get("href") or item.get("url") or ""

            lines.append(f"{i}. {title}")
            if body:
                snippet = body[:300] + ("..." if len(body) > 300 else "")
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

        return ActionResult.success("\n".join(lines), results=results)


class FetchPageTool(Tool):
    name = "website_padho"
    description = (
        "Kisi website ka content padho. URL do, main us page ka text nikaal "
        "ke dunga. Search ke baad detail chahiye to ye use kar."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Page ka URL"},
            "max_chars": {
                "type": "integer",
                "description": "Max kitna text (default 6000)",
            },
        },
        "required": ["url"],
    }

    async def run(
        self, ctx: ToolContext, url: str, max_chars: int = 6000
    ) -> ActionResult:
        # http:// ko https:// bana do (security)
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        elif not url.startswith("https://"):
            url = "https://" + url

        max_chars = max(500, min(int(max_chars), 20000))

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(url)
        except httpx.RequestError as exc:
            return ActionResult.failure(f"Page khul nahi paya: {exc}")

        if response.status_code >= 400:
            return ActionResult.failure(
                f"HTTP {response.status_code} — page nahi mila ya access nahi hai"
            )

        content_type = response.headers.get("content-type", "")

        # JSON API ho to seedha do
        if "application/json" in content_type:
            body = response.text
            if len(body) > max_chars:
                body = body[:max_chars] + "\n... (aur bhi hai)"
            return ActionResult.success(body, url=url, content_type="json")

        if "text/html" not in content_type and "text/" not in content_type:
            return ActionResult.failure(
                f"Ye page text nahi hai ({content_type}) — padh nahi sakta"
            )

        text = _html_to_text(response.text, max_chars=max_chars)

        if not text:
            return ActionResult.failure(
                "Page khali lag raha hai. Ho sakta hai JavaScript se load hota hai "
                "— aise pages ke liye browser automation chahiye (Phase 3)."
            )

        return ActionResult.success(
            f"[{url}]\n\n{text}", url=url, content_type="html"
        )


def _normalize_url(raw: str) -> str:
    """http:// ko https:// karo, scheme na ho to laga do."""
    clean = raw.strip()
    if clean.startswith("http://"):
        return "https://" + clean[len("http://") :]
    if not clean.startswith("https://"):
        return "https://" + clean
    return clean


def _looks_like_domain(text: str) -> bool:
    """'youtube.com' domain hai, 'tum hi ho gaana' nahi."""
    return "." in text and " " not in text and not text.startswith(".")


def resolve_target(url: str, search: str = "") -> str:
    """
    User/LLM ne jo diya usse ek chalne wala URL banao.

    Ye jaan-boojh ke UDAAR hai. LLM kabhi poora URL deta hai, kabhi
    sirf "youtube" likh deta hai. Dono chalne chahiye — warna agent
    ek extra step barbaad karta hai (ya "URL galat hai" bolke ruk
    jaata hai, jo user ke liye sabse irritating cheez hai).

    >>> resolve_target("youtube", "tum hi ho")
    'https://www.youtube.com/results?search_query=tum+hi+ho'
    >>> resolve_target("youtube")
    'https://www.youtube.com'
    """
    from urllib.parse import quote_plus

    raw = (url or "").strip()
    query = (search or "").strip()
    lookup = raw.lower().rstrip("/")

    # --- Search karna hai ---
    if query:
        # "youtube" + query -> "youtube search" template
        template = COMMON_URLS.get(f"{lookup} search")
        if template and "{q}" in template:
            return template.replace("{q}", quote_plus(query))

        # Site ka apna template hai? (maps waghairah)
        direct = COMMON_URLS.get(lookup)
        if direct and "{q}" in direct:
            return direct.replace("{q}", quote_plus(query))

        # Site ka naam pata nahi — Google pe site ke saath dhoondh lo
        term = f"{raw} {query}".strip() if raw else query
        return f"https://www.google.com/search?q={quote_plus(term)}"

    if not raw:
        return ""

    # --- Sirf target diya ---
    if raw.startswith(("http://", "https://")):
        return _normalize_url(raw)

    known = COMMON_URLS.get(lookup)
    if known and "{q}" not in known:
        return known

    if _looks_like_domain(raw):
        return _normalize_url(raw)

    # Naam hai, URL nahi, search bhi nahi — Google pe dhoondh lo
    return f"https://www.google.com/search?q={quote_plus(raw)}"


class OpenWebsiteTool(Tool):
    """
    Website kholna — TAB SAFETY ke saath.

    PEHLE KYA GALAT THA (asli bug jo user ne pakda):
        Ye `webbrowser.open(url)` call karta tha. Python ka default
        `new=0` hai, jiska matlab hai "same browser window mein khol
        do" — aur `autoraise=True` window ko zabardasti aage le aata
        hai. Nateeja: user kuch padh raha hota, agent ne kaam kiya,
        aur user ka TAB SWITCH ho gaya / replace ho gaya.

    AB KYA HOTA HAI:
        1. mode 'agent'  -> SAARTHI ki APNI browser window (Playwright).
                            User ke personal Chrome ko haath hi nahi
                            lagta. Ye sabse safe hai.
        2. mode 'system' -> user ka normal browser, par:
                              new=2        -> NAYA TAB (current replace
                                              nahi hoga)
                              autoraise=False -> window aage laane ki
                                              koshish nahi karega
        3. mode 'auto'   -> Playwright ho to (1), warna (2). DEFAULT.

    IMAANDAAR BAAT: 'system' mode mein Chrome KHUD naye tab pe switch
    kar deta hai. Ye Chrome ka behaviour hai, iska koi command-line
    flag nahi hai. Tab switch bilkul nahi chahiye to 'agent' mode.
    """

    name = "website_kholo"
    description = (
        "Browser mein website kholo (laptop pe). YE BAHUT KAAM KA HAI: "
        "phone connected na ho to bahut kaam browser se ho jaate hain — "
        "YouTube pe gaana, WhatsApp Web pe message, IRCTC pe train, "
        "Instagram, Gmail, Maps, shopping. Phone na ho to app_kholo ki "
        "jagah YE use kar.\n"
        "EK HI CALL MEIN kaam ho jaata hai — do step mat lo:\n"
        "  url='youtube', search='tum hi ho'   (search karna ho)\n"
        "  url='youtube'                        (bas site kholni ho)\n"
        "  url='https://web.whatsapp.com'       (poora URL bhi chalega)\n"
        "Ye NAYE TAB mein khulta hai — user ka chalu kaam nahi todta."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "Site ka naam ('youtube', 'irctc') ya poora URL "
                    "('https://web.whatsapp.com'). Dono chalte hain."
                ),
            },
            "search": {
                "type": "string",
                "description": (
                    "Us site pe kya dhoondhna hai, jaise 'tum hi ho'. "
                    "Isse ek hi step mein search result khul jaata hai."
                ),
            },
        },
        "required": ["url"],
    }

    async def run(
        self, ctx: ToolContext, url: str, search: str = ""
    ) -> ActionResult:
        target = resolve_target(url, search)
        if not target:
            return ActionResult.failure("URL khali hai — kya kholna hai bata")

        mode = getattr(ctx.settings, "browser_mode", "auto")

        # --- Agent ka apna browser (tab bilkul safe) ---
        if mode in ("auto", "agent"):
            result = await self._open_in_agent_browser(ctx, target)

            if result is not None and result.ok:
                return result

            # Fail hua — par KYUN fail hua, ye farak karta hai:
            #
            #   setup problem (playwright/chromium nahi hai)
            #       -> auto mode system browser pe chala jaaye. User ka
            #          kaam hona zyada important hai (prompt rule #8:
            #          "haar mat maano").
            #
            #   asli problem (site khuli nahi, timeout)
            #       -> fallback bekaar hai, wahi error doosre browser mein
            #          bhi aayega. Seedha bata do.
            setup_problem = result is None or bool(result.data.get("setup_error"))

            if not setup_problem:
                return result

            if mode == "agent":
                # User ne saaf bola 'agent' — chup-chaap uske personal
                # browser pe jaana galat hoga, wahi to bachana tha
                device = ctx.devices.get("browser")
                setup = (
                    device.setup_help()
                    if device is not None and hasattr(device, "setup_help")
                    else "pip install playwright && playwright install chromium"
                )
                return ActionResult.failure(
                    "browser_mode='agent' set hai par agent ka browser "
                    "available nahi hai.\n\n"
                    f"{setup}\n\n"
                    "Ya .env mein SAARTHI_BROWSER_MODE=system kar de "
                    "(tera normal browser use hoga — naye tab mein)."
                )

        # --- System browser (naya tab, focus na chheeno) ---
        return await self._open_in_system_browser(target)

    @staticmethod
    async def _open_in_agent_browser(
        ctx: ToolContext, target: str
    ) -> ActionResult | None:
        """
        SAARTHI ke apne browser mein kholo.

        Returns:
            ActionResult agar ho gaya/fail hua, ya None agar agent ka
            browser hi available nahi hai (caller fallback kare).
        """
        device = ctx.devices.get("browser")
        if device is None:
            return None

        try:
            if not await device.is_available():
                return None
        except Exception:  # noqa: BLE001
            return None

        result = await device.launch_app(target)

        if result.ok:
            tabs = result.data.get("tab_count") or 1
            note = (
                "Agent ke apne browser mein naye tab mein khol diya — "
                "tere personal browser ke tabs waise hi hain."
            )
            if tabs > 1:
                note += f" (agent ke {tabs} tab khule hain)"
            return ActionResult.success(
                f"{note}\n{result.output}", url=target, tab_count=tabs
            )

        return result

    @staticmethod
    async def _open_in_system_browser(target: str) -> ActionResult:
        """
        User ke default browser mein kholo — kam se kam nuksaan ke saath.

        new=2         -> NAYA TAB. Default new=0 current tab replace kar
                         sakta hai. Yahi original bug tha.
        autoraise=False -> window ko zabardasti aage na laao.
        """
        import webbrowser

        try:
            # webbrowser stdlib mein hai — Windows/Mac/Linux sab pe chalta
            # hai, koi shell command nahi, koi extra dependency nahi.
            opened = await asyncio.to_thread(
                lambda: webbrowser.open(target, new=2, autoraise=False)
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Browser khul nahi paya: {exc}")

        if not opened:
            return ActionResult.failure(
                f"Browser khul nahi paya. Khud khol le: {target}"
            )

        return ActionResult.success(
            f"Naye tab mein khol diya: {target}\n"
            "  (tera current tab waise hi hai)",
            url=target,
        )


# Aam kaam -> ready URL. LLM ko ye help karta hai sahi URL banane mein.
COMMON_URLS: dict[str, str] = {
    "youtube search": "https://www.youtube.com/results?search_query={q}",
    "youtube": "https://www.youtube.com",
    "google search": "https://www.google.com/search?q={q}",
    "whatsapp web": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com/?q={q}",
    "irctc": "https://www.irctc.co.in",
    "flipkart search": "https://www.flipkart.com/search?q={q}",
    "amazon search": "https://www.amazon.in/s?k={q}",
    "instagram": "https://www.instagram.com",
}


def web_tools() -> list[Tool]:
    """Saare web tools."""
    return [
        WebSearchTool(),
        FetchPageTool(),
        OpenWebsiteTool(),
    ]
