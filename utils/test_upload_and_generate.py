import asyncio
import os
from playwright.async_api import async_playwright

async def test_upload():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    img_path = os.path.abspath("assets/sample_prod1.jpg")
    print(f"Uploading file: {img_path}")

    file_input = page.locator("input[type='file']").first
    if await file_input.count() > 0:
        await file_input.set_input_files([img_path])
        print("Set input files successfully!")
        await asyncio.sleep(2)
    else:
        print("File input not found!")

    # Check screenshot after file upload
    os.makedirs("output/debug", exist_ok=True)
    await page.screenshot(path="output/debug/after_upload.png")
    print("Screenshot saved to output/debug/after_upload.png")

    # Now type prompt and send
    composer = page.locator("textarea[placeholder='Message']").first
    if await composer.count() > 0:
        await composer.fill("Tạo một video review ngắn giới thiệu về sản phẩm trong ảnh này")
        await asyncio.sleep(1)
        send_btn = page.locator("button[aria-label='Send']").first
        if await send_btn.count() > 0 and await send_btn.is_visible():
            await send_btn.click()
        else:
            await composer.press("Enter")
        print("Prompt submitted!")

        # Wait 15 seconds to see what Muse AI replies
        await asyncio.sleep(15)
        await page.screenshot(path="output/debug/after_submit_with_image.png")
        print("Screenshot saved to output/debug/after_submit_with_image.png")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(test_upload())
