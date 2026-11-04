"""Subscription import feedback against synthetic APIs; no production writes."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve

MESSAGE=('This Xiaoyuzhou public page does not expose its subscription list. '
         'A public profile or subscription count is not enough to import it. '
         'You can add individual podcast share links in Podcasts > Add Podcast. '
         'No subscriptions were imported.')
URL='https://www.xiaoyuzhoufm.com/user/0123456789abcdef01234567'

async def check(browser,origin,width,design,theme,output):
    context=await context_for(browser,width)
    calls=[]
    async def respond(route):
        calls.append(route.request.post_data_json)
        if len(calls)==1:
            await route.fulfill(status=422,json={'detail':MESSAGE})
        elif len(calls)==2:
            await route.fulfill(json={'total_found':1,'newly_added':1,'already_subscribed':0,'failed':0,'podcasts':['Synthetic fixture']})
        else:
            await route.fulfill(status=502,content_type='text/html',body='<html>private upstream debug page</html>')
    await context.route('**/api/podcasts/import-subscriptions',respond)
    try:
        page=await context.new_page();await page.goto(origin+'/settings')
        await choose(page,design,theme);await page.reload()
        await page.get_by_role('button',name='Tools & Data',exact=True).click()
        field=page.get_by_label('Xiaoyuzhou user ID or profile URL',exact=True)
        await field.fill(URL)
        await page.get_by_role('button',name='Import',exact=True).click()
        await page.get_by_text(MESSAGE,exact=True).wait_for()
        assert await field.input_value()==URL
        assert not await page.get_by_text('Import Complete',exact=True).count()
        link=page.get_by_role('link',name='Podcasts → Add Podcast',exact=True)
        assert await link.get_attribute('href')=='/podcasts'
        await field.scroll_into_view_if_needed()
        await page.screenshot(path=str(output/f'{width}-{design}-{theme}-unavailable.png'),full_page=True)
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
        await page.get_by_role('button',name='Import',exact=True).click()
        await page.get_by_text('Import Complete',exact=True).wait_for()
        assert await field.input_value()==''
        assert calls==[{'username':URL},{'username':URL}]
        await field.fill(URL);await page.get_by_role('button',name='Import',exact=True).click()
        await page.get_by_text('website gateway returned an error page',exact=False).wait_for()
        assert not await page.get_by_text('private upstream debug page',exact=False).count()
        assert await field.input_value()==URL
        print(json.dumps({'width':width,'design':design,'theme':theme,'result':'passed'}),flush=True)
    finally:await context.close()

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path')
    parser.add_argument('--webkit',action='store_true');parser.add_argument('--widths',type=int,nargs='+',default=[390,820,1440])
    parser.add_argument('--output',type=Path,default=Path('/tmp/subscription-import-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for width in args.widths:
                    for design in ('classic','editorial'):
                        for theme in ('dark','light'):
                            await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,args.output)
            finally:await browser.close()
    finally:server.shutdown();server.server_close()

if __name__=='__main__':asyncio.run(main())
