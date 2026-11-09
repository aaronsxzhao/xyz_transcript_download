"""Local fixture regression: virtual channel grouping, paging, reload and themes."""
import asyncio, json, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures
from playwright.async_api import async_playwright, expect

async def main():
    server=serve(Path('web/dist').resolve())
    output=Path('appearance-checks/unassigned');output.mkdir(parents=True,exist_ok=True)
    results=[]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,chromium_sandbox=True)
            for design,theme in [('classic','light'),('classic','dark'),('editorial','light'),('editorial','dark')]:
                for width,height in [(1440,900),(768,1024),(390,844)]:
                    context=await context_for(browser,width)
                    await context.add_init_script(f"localStorage.setItem('xyz_design', '{design}');")
                    base,_=fixtures()
                    base={k:v for k,v in base.items() if k not in ('transcript','markdown','versions')}
                    tasks=[{**base,'id':f'u{i}','channel':'','title':f'Unassigned lesson {i:02}', 'duration':20,'created_at':f'2026-11-09T00:00:{i:02}Z'} for i in range(43)]
                    groups=[dict(channel='__unknown__',platform='youtube',channel_url='',channel_avatar='',thumbnail='',total=43,done=43,last_updated='2026-11-09'),dict(channel='Named source',platform='youtube',channel_url='https://example.com/channel',channel_avatar='',thumbnail='',total=1,done=1,last_updated='2026-11-09')]
                    async def route(r):
                        u=urlparse(r.request.url);q=parse_qs(u.query)
                        if u.path=='/api/video-notes/channels':await r.fulfill(json={'channels':groups})
                        elif u.path=='/api/video-notes/tasks/by-channel':
                            assert q['channel']==['__unknown__']
                            rows=tasks
                            if q.get('q'):rows=[t for t in rows if q['q'][0] in t['title']]
                            if q.get('sort')==['oldest']:rows=list(reversed(rows))
                            start=40 if q.get('cursor') else 0
                            await r.fulfill(json={'tasks':rows[start:start+40],'next_cursor':'more' if len(rows)>start+40 else None})
                        else:await r.fallback()
                    await context.route('**/api/**',route)
                    page=await context.new_page();await page.set_viewport_size({'width':width,'height':height})
                    origin=f'http://127.0.0.1:{server.server_port}'
                    await page.goto(origin+'/videos?platform=youtube')
                    await choose(page,design,theme)
                    # Persisted-theme cold reload must retain the same group presentation.
                    await page.reload()
                    await expect(page.get_by_role('heading',name='未归属频道',exact=True)).to_be_visible()
                    assert await page.locator('.video-task-list').count()==0
                    assert await page.get_by_role('heading',name='Named source',exact=True).count()==1
                    await page.screenshot(path=str(output/f'group-{design}-{theme}-{width}.png'))
                    await page.get_by_role('button',name='Open videos from 未归属频道',exact=True).click()
                    await expect(page.get_by_role('heading',name='Unassigned lesson 00',exact=True)).to_be_visible()
                    await page.get_by_role('button',name='Show more videos',exact=True).click()
                    await expect(page.get_by_role('heading',name='Unassigned lesson 42',exact=True)).to_be_visible()
                    assert await page.get_by_role('button',name='Show more videos',exact=True).count()==0
                    search=page.get_by_role('textbox',name='Search videos',exact=True)
                    await search.fill('lesson 42')
                    await expect(page.get_by_role('heading',name='Unassigned lesson 00',exact=True)).to_have_count(0)
                    await search.fill('')
                    await expect(page.get_by_role('heading',name='Unassigned lesson 00',exact=True)).to_be_visible()
                    await page.reload()
                    await expect(page.get_by_role('heading',name='未归属频道',exact=True)).to_be_visible()
                    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                    await page.screenshot(path=str(output/f'videos-{design}-{theme}-{width}.png'))
                    results.append({'design':design,'theme':theme,'viewport':[width,height],'passed':True})
                    await context.close()
            await browser.close()
    finally:server.shutdown()
    (output/'assertions.json').write_text(json.dumps(results,indent=2))
    print(f'PASS {len(results)} theme/viewport cases; screenshots require separate inspection')

if __name__=='__main__':asyncio.run(main())
