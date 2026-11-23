import asyncio
import os
from playwright.async_api import async_playwright

async def inspect():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://muse.ai", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)
    
    print("Page URL:", page.url)
    print("Page Title:", await page.title())
    
    # Check cookies
    cookies = await ctx.cookies()
    print("Cookies count:", len(cookies))
    for c in cookies:
        if "muse" in c.get("domain", ""):
            print("Cookie:", c.get("name"), "Domain:", c.get("domain"))
            
    # Try navigating to studio or dashboard
    print("Checking https://muse.ai/dashboard ...")
    try:
        await page.goto("https://muse.ai/dashboard", timeout=15000)
        await asyncio.sleep(2)
        print("Dashboard URL:", page.url)
    except Exception as e:
        print("Dashboard err:", e)

    # Take screenshot of what the browser actually sees
    os.makedirs("output/debug", exist_ok=True)
    await page.screenshot(path="output/debug/current_page.png")
    print("Debug screenshot saved to output/debug/current_page.png")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(inspect())
