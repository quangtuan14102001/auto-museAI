import asyncio
from playwright.async_api import async_playwright

async def inspect_submit():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(2)

    composer = page.locator("textarea[placeholder='Message']").first
    await composer.fill("Test prompt")
    await asyncio.sleep(1)

    # Find buttons near composer or with send icon
    for btn in await page.locator("button").all():
        aria = await btn.get_attribute("aria-label") or ""
        txt = (await btn.inner_text()).strip()
        cl = await btn.get_attribute("class") or ""
        if any(w in aria.lower() for w in ["send", "submit", "message", "generate", "arrow", "enter"]) or "submit" in cl.lower():
            print(f"Candidate submit button: text='{txt}' aria='{aria}' class='{cl[:40]}'")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(inspect_submit())
