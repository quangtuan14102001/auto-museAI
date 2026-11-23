"""Recover an already submitted reference image; never sends a Muse prompt."""
import asyncio
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from playwright.async_api import async_playwright
from config.settings import SettingsManager
from core.muse_session import wait_for_session
from utils.file_utils import find_chromium_executable
from workers.automation_worker import AutomationWorker


async def main():
    manifest = Path(sys.argv[1]).resolve()
    data = json.loads(manifest.read_text(encoding='utf-8'))
    ref = next(r for r in data['references'] if r['id'] == sys.argv[2])
    settings = SettingsManager(str(ROOT/'dist/config/project_config.json'))
    profile = next(p for p in settings.profiles if p.id == data['profile_id'])
    evidence = ROOT/'build/reference-recovery'
    evidence.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as engine:
        context = await engine.chromium.launch_persistent_context(profile.path, headless=False,
            executable_path=find_chromium_executable(), args=['--no-first-run'],
            viewport={'width':1366,'height':768})
        try:
            page = await context.new_page()
            await page.goto(ref['submission_url'] or settings.muse_selectors.studio_url, wait_until='domcontentloaded')
            state = await wait_for_session(page)
            print('Session:',state,flush=True)
            if state != 'authenticated':
                await page.screenshot(path=str(evidence/'session.png'))
                return
            await asyncio.sleep(22)
            prompt = ref['submitted_prompt']
            print('Exact prompt matches:', await page.get_by_text(prompt,exact=True).count(),flush=True)
            anchor = page.get_by_text(prompt,exact=True).last
            if await anchor.count():
                print('Prompt ancestors:',await anchor.evaluate("el=>{let a=[];for(let x=el;x&&a.length<5;x=x.parentElement)a.push({tag:x.tagName,cls:x.className,pel:x.getAttribute('data-pel-impression')});return a}"),flush=True)
                await anchor.evaluate("el=>(el.closest('[data-pel-impression=\"chat_message_impression\"]')||el).scrollIntoView({block:'center'})")
                await asyncio.sleep(3)
            print('Description matches:', await page.get_by_text(ref['description'],exact=False).count(),flush=True)
            print('Page summary:', (await page.locator('body').inner_text())[-1800:],flush=True)
            print('Buttons:',await page.locator('button').evaluate_all("els=>els.map(e=>({text:e.innerText,label:e.getAttribute('aria-label')})).filter(x=>x.text||x.label).slice(0,25)"),flush=True)
            await page.screenshot(path=str(evidence/'before.png'))
            (evidence/'page.html').write_text(await page.content(),encoding='utf-8')
            print(json.dumps(await page.locator('img,video').evaluate_all("""els => els.map(el=>({
              tag:el.tagName,alt:el.alt,label:el.closest('button')?.getAttribute('aria-label'),
              width:el.naturalWidth||el.videoWidth,height:el.naturalHeight||el.videoHeight,
              scheme:(el.currentSrc||el.src||'').split(':')[0]
            }))""")),flush=True)
            worker = AutomationWorker([],[],[],settings.muse_selectors,output_dir=str(evidence/'downloads'))
            if '--full' in sys.argv:
                boundary = await worker._muse_request_boundary(page,prompt)
                for card in await page.locator('button[aria-label^="Open generated image" i]').all():
                    if await card.evaluate("(el,b)=>!b.start.contains(el)&&!!(b.start.compareDocumentPosition(el)&Node.DOCUMENT_POSITION_FOLLOWING)&&(!b.end||!!(el.compareDocumentPosition(b.end)&Node.DOCUMENT_POSITION_FOLLOWING))",boundary):
                        await card.click()
                        await asyncio.sleep(3)
                        break
                await page.screenshot(path=str(evidence/'full-image.png'))
                download = page.locator('[role="dialog"] button[aria-label*="download" i]').first
                print('Viewer buttons:',await page.locator('[role="dialog"] button').evaluate_all("els=>els.map(e=>({text:e.innerText,label:e.getAttribute('aria-label')}))"),flush=True)
                if await download.count():
                    async with page.expect_download(timeout=20000) as pending:
                        await download.click()
                    item = await pending.value
                    target = evidence / ('original_' + Path(item.suggested_filename).name)
                    await item.save_as(str(target))
                    print('Downloaded original:',str(target),flush=True)
                    (evidence/'full-result.json').write_text(json.dumps({'file':str(target),'reference_id':ref['id'],'manifest':str(manifest)}),encoding='utf-8')
                    return
                # The open viewer displays the original above the chat. Take
                # the largest visible decoded image, not a hidden chat collage.
                candidates=await page.locator('[role="dialog"] img').evaluate_all("els=>els.filter(e=>e.getBoundingClientRect().width>0&&e.naturalWidth>=1024).map(e=>({src:e.currentSrc||e.src,pixels:e.naturalWidth*e.naturalHeight})).sort((a,b)=>b.pixels-a.pixels)")
                if candidates:
                    body=await worker._fetch_result_bytes(page,candidates[0]['src'])
                    full=worker._save_result_bytes(body,profile.name,0,'image')
                    print('Full resolution recovered file:',full,flush=True)
                    if full:
                        (evidence/'full-result.json').write_text(json.dumps({'file':full,'reference_id':ref['id'],'manifest':str(manifest)}),encoding='utf-8')
                return
            output = await worker._check_dom_real_media(page,profile.name,0,set(),0,True,set(),set(),prompt)
            print('Recovered file:',output,flush=True)
            if output:
                (evidence/'result.json').write_text(json.dumps({'file':output,'reference_id':ref['id'],'manifest':str(manifest)}),encoding='utf-8')
        finally:
            await context.close()


if __name__ == '__main__':
    asyncio.run(main())
