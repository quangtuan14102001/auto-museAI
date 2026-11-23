import asyncio
from playwright.async_api import async_playwright

async def test_live_send():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    # Listen to all network responses after submission
    received_responses = []
    def log_resp(resp):
        url = resp.url
        content_type = resp.headers.get("content-type", "")
        status = resp.status
        if any(ext in url for ext in [".webp", ".png", ".jpg", ".mp4", "api", "chat", "completion", "generate"]):
            received_responses.append((url[:70], status, content_type[:30]))

    page.on("response", log_resp)

    # Find composer
    composer = page.locator("textarea[placeholder='Message']").first
    if await composer.count() > 0:
        print("Found composer. Typing test message...")
        await composer.fill("Xin chào Muse AI, bạn có thể làm được gì?")
        await asyncio.sleep(1)

        # Press Enter or click send
        send_btn = page.locator("button[aria-label='Send']").first
        if await send_btn.count() > 0 and await send_btn.is_visible():
            print("Clicking Send button...")
            await send_btn.click()
        else:
            print("Pressing Enter...")
            await composer.press("Enter")

        print("Waiting 10 seconds to observe Muse AI response...")
        for sec in range(10):
            await asyncio.sleep(1)
            print(f"Elapsed {sec+1}s, received responses count: {len(received_responses)}")

        print("\nLast 10 responses:")
        for r in received_responses[-10:]:
            print(" ->", r)

        # Take screenshot of chat reply
        await page.screenshot(path="output/debug/live_chat_response.png")
        print("Chat screenshot saved to output/debug/live_chat_response.png")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(test_live_send())
