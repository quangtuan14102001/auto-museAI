import asyncio
from playwright.async_api import async_playwright

async def test_composer():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    # Find the real textarea
    composer = page.locator("textarea[placeholder='Message'], textarea[aria-label='Message']").first
    print("Composer found:", await composer.count() > 0)
    if await composer.count() > 0:
        await composer.click()
        await composer.fill("Xin chào Muse AI, thử nghiệm tạo ảnh")
        print("Filled message into composer successfully!")
        await page.screenshot(path="output/debug/filled_composer.png")
        print("Screenshot saved to output/debug/filled_composer.png")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(test_composer())
