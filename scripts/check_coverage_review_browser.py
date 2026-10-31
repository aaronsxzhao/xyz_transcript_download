"""Coverage retry feedback and saved-note preservation on narrow screens."""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures
from summary_errors import _EN_NOTICES
from playwright.async_api import async_playwright


async def main():
    server=serve(Path('web/dist').resolve())
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            for design,theme in [('classic','dark'),('classic','light'),('editorial','light'),('editorial','dark')]:
                for width in [390,820]:
                    task,_=fixtures()
                    task.update(platform='youtube',markdown=_EN_NOTICES['audit']+'\n\n# Saved course\n\nExisting argument remains readable during review.')
                    count=[0]
                    context=await context_for(browser,width)
                    async def api(route):
                        path=urlparse(route.request.url).path
                        if path=='/api/video-notes/tasks/bench':await route.fulfill(json=task)
                        elif path=='/api/video-notes/tasks/bench/review-coverage':
                            count[0]+=1
                            task.update(status='summarizing',progress=42,message='Coverage review · 4/9 source sections reviewed')
                            await route.fulfill(json={'task_id':'bench'})
                        else:await route.fallback()
                    await context.route('**/api/**',api)
                    page=await context.new_page()
                    await page.goto(f'http://127.0.0.1:{server.server_port}/videos/bench')
                    await choose(page,design,theme)
                    await page.get_by_role('button',name='Retry coverage review',exact=True).click()
                    button=page.get_by_role('button',name='Review in progress…',exact=True)
                    await button.wait_for()
                    assert await button.is_disabled() and count[0]==1
                    await page.reload()
                    await button.wait_for()
                    assert await page.locator('.reader-body').inner_text()
                    assert 'Existing argument remains readable' in await page.locator('.reader-body').inner_text()
                    assert await page.get_by_role('progressbar').count()>0
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    await page.screenshot(path=f'/tmp/coverage-review-{design}-{theme}-{width}.png')
                    print(json.dumps({'design':design,'theme':theme,'width':width,'readable':True,'reload_progress':True,'overflow':False}),flush=True)
                    await context.close()
            await browser.close()
    finally:server.shutdown()

if __name__=='__main__':asyncio.run(main())
