"""Podcast subscription/upload pending and retry checks using synthetic responses."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve

async def check(browser, origin, width, design, theme, output):
    for upload in [False, True]:
        context = await context_for(browser, width)
        page = await context.new_page()
        release, started = asyncio.Event(), asyncio.Event()
        requests = []
        async def response(route):
            if route.request.method != 'POST':
                await route.fulfill(json=[])
                return
            requests.append(route.request.post_data)
            started.set()
            await release.wait()
            await route.fulfill(status=400, json={'detail':'Synthetic failure. Please retry.'})
        await context.route('**/api/podcasts'+('/upload-audio' if upload else ''), response)
        try:
            await page.goto(origin+'/podcasts')
            await choose(page, design, theme)
            await page.get_by_role('button', name='Upload Audio' if upload else 'Add Podcast', exact=True).click()
            if upload:
                await page.get_by_label('Audio file', exact=True).set_input_files({'name':'fixture.wav','mimeType':'audio/wav','buffer':b'synthetic audio'})
                await page.get_by_label('Episode title', exact=True).fill('Keep this title')
                await page.get_by_label('Description', exact=True).fill('Keep these notes')
            else:
                await page.get_by_label('Podcast URL', exact=True).fill('https://www.xiaoyuzhoufm.com/podcast/long-synthetic-url')
                field = await page.get_by_label('Podcast URL', exact=True).bounding_box()
                hint = await page.locator('form span').filter(has_text='小宇宙').bounding_box()
                assert hint['y'] >= field['y']+field['height'], 'Platform hint overlaps URL'
            form = page.locator('form')
            submit = page.get_by_role('button', name='Upload' if upload else 'Add', exact=True)
            await submit.click()
            await asyncio.wait_for(started.wait(), 10)
            assert await form.get_attribute('aria-busy') == 'true'
            assert await form.locator('input:enabled,textarea:enabled').count() == 0
            for label in ['Add Podcast','Upload Audio']:
                assert await page.get_by_role('button', name=label, exact=True).is_disabled()
            await form.dispatch_event('submit')
            await page.wait_for_timeout(100)
            assert len(requests) == 1
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(output/f'{width}-{design}-{theme}-{upload}-pending.png'), full_page=True)
            release.set()
            await page.get_by_text('Synthetic failure. Please retry.', exact=True).wait_for()
            if theme == 'light':
                contrast = await page.locator('.toast-stack [role="alert"]').first.evaluate("""e => {
                    const lum = c => {const v=c.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};
                    const bg=lum(getComputedStyle(e).backgroundColor);
                    return Math.min(...[...e.querySelectorAll('p')].map(p=>{const fg=lum(getComputedStyle(p).color);return (Math.max(bg,fg)+.05)/(Math.min(bg,fg)+.05)}));
                }""")
                assert contrast >= 4.5, ('Unreadable notification', contrast)
            assert await submit.is_enabled()
            assert await form.get_attribute('aria-busy') == 'false'
            if upload:
                assert await page.get_by_label('Episode title', exact=True).input_value() == 'Keep this title'
                assert await page.get_by_label('Audio file', exact=True).evaluate('e=>e.files[0].name') == 'fixture.wav'
            else:
                assert 'long-synthetic-url' in await page.get_by_label('Podcast URL', exact=True).input_value()
            await submit.click()
            await page.wait_for_function('document.querySelector("form").getAttribute("aria-busy")==="false"')
            assert len(requests) == 2
            await page.wait_for_timeout(400)
            await page.screenshot(path=str(output/f'{width}-{design}-{theme}-{upload}-retry.png'), full_page=True)
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            print(json.dumps({'width':width,'design':design,'theme':theme,'upload':upload,'result':'passed'}), flush=True)
        finally:
            release.set()
            await context.close()

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit', action='store_true')
    parser.add_argument('--widths', type=int, nargs='+', default=[390,820])
    parser.add_argument('--output', type=Path, default=Path('/tmp/podcast-form-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for width in args.widths:
                    for design in ['classic','editorial']:
                        for theme in ['dark','light']:
                            await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,args.output)
            finally: await browser.close()
    finally: server.shutdown();server.server_close()

if __name__=='__main__': asyncio.run(main())
