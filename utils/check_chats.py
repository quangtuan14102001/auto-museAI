import asyncio
from playwright.async_api import async_playwright

async def check_chats():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    print("Current page URL:", page.url)

    # Click on the latest chat or inspect chat list
    chats_btn = page.locator("button:has-text('Chats')").first
    if await chats_btn.count() > 0:
        await chats_btn.click()
        await asyncio.sleep(2)
        print("Clicked Chats button")

        # List all chat items
        chat_links = await page.locator("a[href*='/c/'], [role='option'], button:has-text('video')").all()
        print(f"Chat items found: {len(chat_links)}")
        for idx, cl in enumerate(chat_links[:5]):
            txt = (await cl.inner_text()).strip()
            print(f"  Chat #{idx}: {txt[:40]}")
            if "video" in txt.lower():
                await cl.click()
                await asyncio.sleep(4)
                print("Clicked video chat!")
                break

    # Now inspect videos on page
    videos = await page.locator("video").all()
    print(f"Videos count now: {len(videos)}")
    for idx, v in enumerate(videos):
        src = await v.get_attribute("src") or ""
        is_av = await v.evaluate("el => el.closest('.rounded-full') !== null")
        print(f"  Video #{idx}: src={src[:80]} is_avatar={is_av}")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(check_chats())
