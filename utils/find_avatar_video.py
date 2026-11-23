import asyncio
from playwright.async_api import async_playwright

async def find_avatar_video():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    # Inspect all video elements on page
    videos = await page.locator("video").all()
    print(f"Total video elements on page: {len(videos)}")
    for idx, v in enumerate(videos):
        src = await v.get_attribute("src") or ""
        cl = await v.get_attribute("class") or ""
        aria = await v.get_attribute("aria-label") or ""
        parent = await v.evaluate("el => el.parentElement ? el.parentElement.className : ''")
        print(f"Video #{idx}: src='{src[:100]}' class='{cl[:40]}' parent='{parent[:40]}'")
        
        # Check source tags inside video
        sources = await v.locator("source").all()
        for s in sources:
            s_src = await s.get_attribute("src") or ""
            print(f"  -> Source src='{s_src[:100]}'")

    # Send a prompt and observe video elements
    composer = page.locator("textarea[placeholder='Message']").first
    if await composer.count() > 0:
        await composer.fill("tạo video")
        send_btn = page.locator("button[aria-label='Send']").first
        if await send_btn.count() > 0 and await send_btn.is_visible():
            await send_btn.click()
        else:
            await composer.press("Enter")
        print("Sent prompt 'tạo video'...")

        for sec in range(8):
            await asyncio.sleep(1)
            v_now = await page.locator("video").all()
            print(f"Sec {sec+1}: total videos = {len(v_now)}")
            for idx, v in enumerate(v_now):
                src = await v.get_attribute("src") or ""
                print(f"  v[{idx}]: {src[:80]}")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(find_avatar_video())
