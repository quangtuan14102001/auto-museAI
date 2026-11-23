import asyncio
import base64
from playwright.async_api import async_playwright

async def download_video():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    # Click Chats
    chats_btn = page.locator("button:has-text('Chats')").first
    if await chats_btn.count() > 0:
        await chats_btn.click()
        await asyncio.sleep(2)
        chat_item = page.locator("button:has-text('video'), a:has-text('video')").first
        if await chat_item.count() > 0:
            await chat_item.click()
            await asyncio.sleep(3)

    # Find the non-avatar video
    videos = await page.locator("video").all()
    for v in videos:
        is_av = await v.evaluate("el => el.closest('.rounded-full') !== null")
        if not is_av:
            print("Found non-avatar video! Downloading...")
            b64 = await v.evaluate("""async (el) => {
                const resp = await fetch(el.src || el.currentSrc);
                const blob = await resp.blob();
                return new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                });
            }""")
            data = base64.b64decode(b64)
            with open("output/so1/Prompt_001_real_review.mp4", "wb") as f:
                f.write(data)
            print(f"SUCCESS! Real review video downloaded! Size: {len(data)} bytes.")
            break

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(download_video())
