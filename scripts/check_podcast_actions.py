"""Verify subscription action state and background navigation with synthetic APIs."""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve


async def check(browser, origin, width, design, theme, output):
    context=await context_for(browser,width)
    rows=[{'pid':pid,'title':'Show '+pid,'platform':'apple','author':'Synthetic author','description':'Synthetic subscription for testing concurrent actions','cover_url':'','episode_count':2,'summarized_count':0} for pid in ('one','two')]
    release={pid:asyncio.Event() for pid in ('one','two')}
    requested=[]
    import_release=asyncio.Event();import_started=asyncio.Event()
    async def podcasts(route):
        if route.request.method=='POST':
            import_started.set();await import_release.wait()
            await route.fulfill(json={**rows[0],'resolved_episode_id':'matched'})
        else: await route.fulfill(json=rows)
    async def refresh(route):
        pid=urlparse(route.request.url).path.split('/')[-2]
        requested.append(pid);await release[pid].wait()
        await route.fulfill(json={'message':'Updated','total':2,'new_episodes':0})
    await context.route(re.compile(r'/api/podcasts(?:\?.*)?$'),podcasts)
    await context.route('**/api/podcasts/*/refresh',refresh)
    page=await context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        await page.goto(origin+'/podcasts?platform=apple');await choose(page,design,theme)
        first=page.get_by_role('button',name='Refresh Show one',exact=True)
        second=page.get_by_role('button',name='Refresh Show two',exact=True)
        bulk=page.get_by_role('button',name='Check podcast updates',exact=True)
        await first.click();await second.click()
        await page.wait_for_function("[...document.querySelectorAll('[title=\"Refresh episodes\"]')].every(e=>e.disabled)")
        assert await bulk.is_disabled()
        for pid in ('one','two'):
            assert await page.get_by_role('button',name='Remove Show '+pid,exact=True).is_disabled()
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
        await page.screenshot(path=str(output/f'{width}-{design}-{theme}-concurrent.png'),full_page=True)
        release['one'].set()
        await first.wait_for(state='visible')
        await page.wait_for_function('!document.querySelector(\'[aria-label="Refresh Show one"]\').disabled')
        assert await second.is_disabled()
        assert await second.get_attribute('aria-busy')=='true'
        release['two'].set()
        await page.wait_for_function('!document.querySelector(\'[aria-label="Refresh Show two"]\').disabled')
        assert sorted(requested)==['one','two']
        await page.get_by_role('button',name='Add Podcast',exact=True).click()
        await page.get_by_label('Podcast URL',exact=True).fill('https://open.spotify.com/episode/123')
        await page.get_by_role('button',name='Add',exact=True).click()
        await asyncio.wait_for(import_started.wait(),10)
        if width<768:
            await page.get_by_role('button',name='Open navigation',exact=True).click()
            await page.screenshot(path=str(output/f'{width}-{design}-{theme}-navigation.png'),full_page=True)
        await page.get_by_role('link',name='Library',exact=True).click()
        await page.get_by_role('heading',name='Library',exact=True).wait_for()
        import_release.set()
        await page.get_by_text('Spotify episode matched to public RSS',exact=True).wait_for()
        assert urlparse(page.url).path=='/library'
        assert not errors,errors
        print(json.dumps({'width':width,'design':design,'theme':theme,'independent_pending':True,'no_duplicate_refresh':True,'background_import_keeps_navigation':True,'errors':errors}),flush=True)
    finally:
        for event in release.values(): event.set()
        import_release.set();await context.close()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--output',type=Path,default=Path('/tmp/podcast-action-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            for width in (390,820):
                for design in ('classic','editorial'):
                    for theme in ('dark','light'):
                        await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,args.output)
            await browser.close()
    finally: server.shutdown();server.server_close()

if __name__=='__main__': asyncio.run(main())
