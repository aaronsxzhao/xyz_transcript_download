"""Fault-inject stalled reader chunks; synthetic data, no production writes."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures, serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


async def check(browser, origin, width, output):
    task, _ = fixtures()
    task.update(markdown='# Synthetic review\n\nReadable notes stay available.\n\n![Test chart](/data/screenshots/test.jpg)', versions=[])
    context = await browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block')
    await context.add_init_script('''
      localStorage.setItem('xyz_access_token',TOKEN);
      localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
      window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),1)}close(){}};
    '''.replace('TOKEN', json.dumps(token(int(time.time())+7200))))
    mutations = []
    async def api(route):
        path = urlparse(route.request.url).path
        if route.request.method != 'GET' and path != '/api/performance':
            mutations.append(path)
        body = {}
        if path == '/api/auth/me': body = {'id':'bench','email':'bench@example.com','authenticated':True}
        elif path == '/api/auth/config': body = {'supabase_enabled':True}
        elif path == '/api/video-notes/tasks/bench': body = task
        await route.fulfill(json=body)
    await context.route('**/api/**', api)
    await context.route('**/data/screenshots/**', lambda route: route.fulfill(content_type='image/svg+xml', body='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="#334155"/><text x="40" y="100" fill="white" font-size="32">Synthetic chart</text></svg>'))
    held = asyncio.Event()
    intercepted = []
    async def stall(route):
        intercepted.append(route.request.url)
        await held.wait()
        await route.continue_()
    await context.route('**/RegenerateDialog-*.js', stall)
    page = await context.new_page()
    await page.goto(origin+'/videos/bench')
    await page.get_by_role('heading',name='Synthetic review').wait_for()
    export = page.get_by_role('button',name='Export',exact=True)
    await export.click()
    download = page.get_by_title('Download .md',exact=True)
    await download.focus()
    async with page.expect_download() as pending:
        await page.keyboard.press('Enter')
    assert (await pending.value).suggested_filename.endswith('.md')
    assert await export.evaluate('(e)=>e===document.activeElement')
    menu = page.get_by_role('button',name='More summary actions',exact=True)
    await menu.click()
    await page.get_by_role('button',name='Regenerate summary',exact=True).click()
    failed = page.get_by_role('dialog',name='Confirmation unavailable',exact=True)
    await failed.wait_for(timeout=22000)
    assert intercepted, 'Fault injection did not intercept the confirmation module'
    retry = failed.get_by_role('button',name='Retry loading',exact=True)
    assert await retry.is_visible()
    await retry.focus()
    await page.keyboard.press('Tab')
    assert await failed.get_by_role('button',name='Cancel',exact=True).evaluate('(e)=>e===document.activeElement')
    await page.keyboard.press('Tab')
    assert await retry.evaluate('(e)=>e===document.activeElement')
    await page.screenshot(path=str(output/f'{width}-confirmation-recovery.png'))
    await retry.click()
    held.set()
    dialog = page.get_by_role('dialog',name='Regenerate summary',exact=True)
    await dialog.wait_for()
    await dialog.get_by_role('button',name='Cancel',exact=True).click()
    assert await menu.evaluate('(e)=>e===document.activeElement')
    # Delay the gallery chunk independently; the fallback must retain the original.
    gallery_held = asyncio.Event()
    gallery_requests = []
    async def stall_gallery(route):
        gallery_requests.append(route.request.url)
        await gallery_held.wait()
        await route.continue_()
    await context.route('**/ScreenshotGallery-*.js', stall_gallery)
    await page.get_by_role('button',name='Enlarge Test chart',exact=True).click()
    fallback = page.get_by_role('dialog',name='Enlarged screenshot',exact=True)
    await fallback.get_by_text('Image controls unavailable. Original image:').wait_for(timeout=22000)
    assert gallery_requests, 'Fault injection did not intercept the gallery module'
    await fallback.locator('img').evaluate('(image)=>image.decode()')
    await page.screenshot(path=str(output/f'{width}-gallery-recovery.png'))
    await fallback.get_by_role('button',name='Close',exact=True).click()
    assert await page.get_by_role('heading',name='Synthetic review').is_visible()
    assert not mutations, mutations
    gallery_held.set()
    await context.close()
    return {'width':width, 'menu_action_focus':True, 'modal_retry_and_focus':True, 'gallery_timeout_preserves_original':True, 'mutations':mutations}


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--output',type=Path,default=Path('/tmp/reader-recovery'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            results=[]
            for width in (390,1440):
                result=await check(browser,f'http://127.0.0.1:{server.server_port}',width,args.output)
                results.append(result);print(json.dumps(result),flush=True)
            await browser.close()
            (args.output/'results.json').write_text(json.dumps(results,indent=2))
    finally:
        server.shutdown()

if __name__=='__main__':asyncio.run(main())
