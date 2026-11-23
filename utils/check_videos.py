import asyncio
from playwright.async_api import async_playwright

async def check_videos():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    def on_resp(resp):
        url = resp.url
        ct = resp.headers.get("content-type", "")
        if "mp4" in url or "video" in ct or "webm" in url:
            print("VIDEO RESPONSE DETECTED:", url, "ContentType:", ct)

    page.on("response", on_resp)
    await page.goto("https://muse.ai/", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(5)

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(check_videos())
