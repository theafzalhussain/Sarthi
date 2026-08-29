"""Test if the agent's Playwright browser actually launches + navigates + clicks."""
import sys, asyncio
sys.path.insert(0, ".")
from saarthi.devices.browser import BrowserDevice

async def main():
    dev = BrowserDevice(name="browser")
    print("is_available:", await dev.is_available())

    print("launching youtube search...")
    res = await dev.launch_app("https://www.youtube.com/results?search_query=udariyaan+song")
    print("launch ok:", res.ok, "| error:", res.error[:120] if not res.ok else "-")
    print("data:", {k: v for k, v in (res.data or {}).items() if k != 'image_b64'})

    if res.ok:
        await asyncio.sleep(2)
        page = await dev.read_page(max_chars=300)
        print("page_padho ok:", page.ok, "| text:", (page.output or "")[:150])
        print("\nclicking first video via tap_text('udariyaan')...")
        tap = await dev.tap_text("udariyaan")
        print("tap ok:", tap.ok, "| out:", (tap.output or tap.error)[:150])
        await asyncio.sleep(2)
        # confirm we navigated to a watch page
        try:
            url = dev._page.url if dev._page else "?"
            print("current URL:", url)
            print("PLAYING:" , "watch?v=" in url)
        except Exception as e:
            print("url check err:", e)

    await dev.close() if hasattr(dev, "close") else None

if __name__ == "__main__":
    asyncio.run(main())
