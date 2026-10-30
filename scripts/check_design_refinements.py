"""Exercise statistics, protected deletion and settings semantics with synthetic APIs."""
import argparse
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures
from scripts.check_editorial_components import CONTROL

async def check(browser, origin, width, output):
    context = await context_for(browser, width, touch=True)
    task, _ = fixtures()
    task.update(title='A saved video to keep', channel='Fixture', versions=[])
    requests=[]
    await context.route('**/api/video-notes/tasks/by-channel*', lambda r:r.fulfill(json={'tasks':[task],'next_cursor':None}))
    async def remove(route):
        if route.request.method=='DELETE':requests.append('DELETE')
        await route.fulfill(json={} if route.request.method=='DELETE' else task)
    await context.route('**/api/video-notes/tasks/bench',remove)
    page=await context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        for design in ['editorial','classic']:
            for theme in ['light','dark']:
                await page.goto(origin+'/')
                await page.locator('.collection-stats').wait_for()
                await choose(page,design,theme)
                await page.wait_for_timeout(250)
                assert not await page.get_by_role('button',name='Add content',exact=True).count()
                if design=='editorial':
                    assert not await page.locator('.collection-stats').evaluate('e=>e.open')
                    stats=page.locator('.collection-stats>summary')
                    await stats.focus();await stats.press('Enter')
                    assert await page.locator('.collection-stats').evaluate('e=>e.open')
                    await stats.press('Enter')
                else:
                    assert await page.locator('.collection-stats').evaluate('e=>e.open')
                    assert not await page.locator('.collection-stats>summary').is_visible()
                for path,selector in [('/', '#dashboard-add-content input'),('/library','input[placeholder]'),('/settings','#notion-integration-token')]:
                    await page.goto(origin+path)
                    field=page.locator(selector).first
                    await field.wait_for()
                    await page.wait_for_timeout(250)
                    probe=CONTROL.replace('Math.min(contrast(e),...text.map(s=>contrast(s)))', "contrast(e,'::placeholder',getComputedStyle(e,'::placeholder').color)")
                    result=await field.evaluate(probe)
                    assert result['ratio']>=4.5,(design,theme,path,result['ratio'])
                await page.screenshot(path=str(output/f'{width}-{design}-{theme}-library.png'))
        await page.goto(origin+'/videos?platform=youtube&channel=Fixture')
        await page.locator('.video-task-list h3').wait_for()
        assert not await page.get_by_role('button',name='Re-process A saved video to keep',exact=True).is_visible()
        assert not await page.get_by_text('Publication date unavailable',exact=True).count()
        assert not await page.get_by_role('button',name='All (1)',exact=True).count()
        await page.get_by_label('More actions for A saved video to keep',exact=True).click()
        await page.get_by_role('button',name='Re-process A saved video to keep',exact=True).wait_for()
        for design in ['classic','editorial']:
            for theme in ['light','dark']:
                await choose(page,design,theme);await page.wait_for_timeout(250)
                if not await page.locator('.task-more').first.evaluate('e=>e.open'):
                    await page.get_by_label('More actions for A saved video to keep',exact=True).click()
                await page.wait_for_timeout(200)  # Let newly revealed controls finish their theme transition.
                for button in await page.locator('.task-more button').all():
                    result=await button.evaluate(CONTROL)
                    assert result['ratio']>=4.5,(design,theme,result)
                await page.screenshot(path=str(output/f'{width}-{design}-{theme}-actions.png'))
        async def cancel(dialog):
            assert 'A saved video to keep' in dialog.message
            await dialog.dismiss()
        page.once('dialog',cancel)
        await page.get_by_title('Delete video',exact=True).click()
        assert not requests
        assert await page.locator('.video-task-list h3').count()==1
        page.once('dialog',lambda d:d.accept())
        await page.get_by_title('Delete video',exact=True).click()
        await page.locator('.video-task-list h3').wait_for(state='detached')
        assert requests==['DELETE'],requests
        await page.goto(origin+'/settings')
        await page.get_by_role('button',name='Platform Accounts',exact=True).click()
        await page.get_by_role('button',name='YouTube',exact=True).click()
        paste=page.get_by_role('button',name='Paste Cookies',exact=True)
        await paste.click()
        assert await paste.get_attribute('aria-pressed')=='true'
        await page.get_by_label('Cookie string or cookies.txt content',exact=True).fill('synthetic=fixture')
        await page.get_by_role('button',name='Upload File',exact=True).click()
        assert await paste.get_attribute('aria-pressed')=='false'
        await page.get_by_role('button',name='Tools & Data',exact=True).click()
        await page.get_by_label('Xiaoyuzhou username or profile URL',exact=True).wait_for()
        assert not errors,errors
        print(f'{width}: statistics, placeholder contrast, deletion, settings passed',flush=True)
    finally:
        await context.close()

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('appearance-checks/design-refinements'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for width in [390,820,1440]:await check(browser,f'http://127.0.0.1:{server.server_port}',width,args.output)
            finally:await browser.close()
    finally:server.shutdown();server.server_close()

if __name__=='__main__':asyncio.run(main())
