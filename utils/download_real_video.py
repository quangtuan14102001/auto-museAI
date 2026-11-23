import asyncio
import base64
import os
from playwright.async_api import async_playwright

async def download_real_video():
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context("profiles/so1", headless=True)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://muse.ai/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    # Find the non-avatar video
    videos = await page.locator("video").all()
    target_video = None
    for v in videos:
        is_avatar = await v.evaluate("el => el.closest('.rounded-full') !== null")
        if not is_avatar:
            target_video = v
            break

    if target_video:
        print("Found real generated video element!")
        src = await target_video.get_attribute("src")
        print("Video src:", src)

        # Extract blob bytes via in-page fetch
        b64 = await target_video.evaluate("""async (el) => {
            const resp = await fetch(el.src || el.currentSrc);
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""")
        
        video_bytes = base64.b64decode(b64)
        out_path = "output/debug/real_aothun_video.mp4"
        with open(out_path, "wb") as f:
            f.write(video_bytes)
        print(f"Downloaded real video successfully! Size: {len(video_bytes)} bytes. Saved to {out_path}")
    else:
        print("Could not find non-avatar video element.")

    await ctx.close()
    await p.stop()

if __name__ == "__main__":
    asyncio.run(download_real_video())
