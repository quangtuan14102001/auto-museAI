import asyncio
from playwright.async_api import async_playwright

async def inspect_chat_video():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    print("=== INSPECTING ALL VIDEOS IN CHAT ===")
    videos = await page.locator("video").all()
    print(f"Total video elements: {len(videos)}")
    for idx, v in enumerate(videos):
        src = await v.get_attribute("src") or ""
        cl = await v.get_attribute("class") or ""
        # Check parents
        is_avatar = await v.evaluate("el => el.closest('.rounded-full') !== null")
        is_chat_msg = await v.evaluate("el => el.closest('[data-message]') !== null || el.closest('.chat') !== null || el.closest('main') !== null")
        print(f"Video #{idx}:")
        print(f"  src: {src[:120]}")
        print(f"  is_avatar: {is_avatar}")
        print(f"  class: {cl[:50]}")

    # Inspect download links or buttons on generated videos
    links = await page.locator("a[download], a[href*='.mp4'], button[aria-label*='Download' i]").all()
    print(f"\nTotal download links/buttons: {len(links)}")
    for idx, l in enumerate(links):
        href = await l.get_attribute("href") or ""
        txt = (await l.inner_text()).strip()
        print(f"  Link #{idx}: href='{href[:80]}' text='{txt}'")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(inspect_chat_video())
