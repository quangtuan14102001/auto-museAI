"""Observe Muse's rendered session without reading or exporting credentials."""
import asyncio
import time


async def session_state(page):
    disconnected = page.get_by_text("Muse is disconnected", exact=True)
    if await disconnected.count() and await disconnected.first.is_visible():
        return "disconnected"
    # A usable editor takes precedence over landing-page text during hydration.
    for editor in await page.locator('textarea, [contenteditable="true"]').all():
        if await editor.is_visible() and await editor.is_enabled():
            return "authenticated"
    landing = page.get_by_text("Log in or create an account", exact=True)
    if await landing.count() and await landing.first.is_visible():
        return "signed_out"
    return "unknown"


async def wait_for_session(page, timeout=12):
    deadline = time.monotonic() + timeout
    signed_out_since = None
    authenticated_since = None
    while True:
        state = await session_state(page)
        if state == "disconnected":
            return state
        now = time.monotonic()
        if state == "authenticated":
            authenticated_since = authenticated_since or now
            if now - authenticated_since >= 3:
                return state
        else:
            authenticated_since = None
        if state == "signed_out":
            signed_out_since = signed_out_since or now
            if now - signed_out_since >= 3:
                return state
        else:
            signed_out_since = None
        if now >= deadline:
            return state
        await asyncio.sleep(.5)
