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


class OpenWebsiteTool(Tool):
    name = "website_kholo"
    description = (
        "Browser mein koi website/URL kholo (laptop pe). YE BAHUT KAAM KA "
        "HAI: phone connected na ho to bahut kaam laptop pe browser se ho "
        "jaate hain — YouTube pe gaana, WhatsApp Web pe message, IRCTC pe "
        "train, Instagram, Gmail, Maps, shopping. "
        "Phone na ho to app_kholo ki jagah YE use kar. "
        "Search bhi kar sakta hai: youtube pe gaana chalane ke liye "
        "url='https://www.youtube.com/results?search_query=tum+hi+ho'"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Poora URL, jaise 'https://www.youtube.com'",
            }
        },
        "required": ["url"],
    }

    async def run(self, ctx: ToolContext, url: str) -> ActionResult:
        import webbrowser

        clean = url.strip()
        if not clean:
            return ActionResult.failure("URL khali hai")

        # http:// ko https:// bana do
        if clean.startswith("http://"):
            clean = "https://" + clean[len("http://") :]
        elif not clean.startswith("https://"):
            clean = "https://" + clean

        try:
            # webbrowser stdlib mein hai — Windows/Mac/Linux sab pe chalta
            # hai, koi shell command nahi, koi extra dependency nahi.
            opened = await asyncio.to_thread(webbrowser.open, clean)
        except Exception as exc:  # noqa: BLE001
            return ActionResult.failure(f"Browser khul nahi paya: {exc}")

        if not opened:
            return ActionResult.failure(
                f"Browser khul nahi paya. Khud khol le: {clean}"
            )

        return ActionResult.success(f"Browser mein khol diya: {clean}", url=clean)


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
