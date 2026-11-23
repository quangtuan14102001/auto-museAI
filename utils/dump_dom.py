import asyncio
from playwright.async_api import async_playwright

async def inspect_dom():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)

    print("=== DUMPING ELEMENTS ON https://muse.ai/ ===")
    
    # 1. Textareas & Contenteditables & Inputs
    for el in await page.locator("textarea, input, [contenteditable='true'], [role='textbox']").all():
        tag = await el.evaluate("e => e.tagName")
        placeholder = await el.get_attribute("placeholder") or ""
        aria = await el.get_attribute("aria-label") or ""
        cl = await el.get_attribute("class") or ""
        visible = await el.is_visible()
        print(f"INPUT/TEXTAREA: <{tag}> placeholder='{placeholder}' aria='{aria}' class='{cl[:40]}' visible={visible}")

    # 2. Buttons
    print("\n=== BUTTONS ===")
    for b in await page.locator("button, [role='button'], a.btn").all():
        txt = (await b.inner_text()).strip()
        aria = await b.get_attribute("aria-label") or ""
        visible = await b.is_visible()
        if txt or aria:
            print(f"BUTTON: text='{txt[:30]}' aria='{aria}' visible={visible}")

    # 3. File Inputs
    print("\n=== FILE INPUTS ===")
    for fi in await page.locator("input[type='file']").all():
        accept = await fi.get_attribute("accept") or ""
        print(f"FILE INPUT: accept='{accept}'")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(inspect_dom())
