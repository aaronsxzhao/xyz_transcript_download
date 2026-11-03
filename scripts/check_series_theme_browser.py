"""Cold-start series regression: production CSS cascade and grouped pagination."""
import asyncio,json,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for,choose
from scripts.check_library_browser import serve
from scripts.check_series_browser import note
from playwright.async_api import async_playwright
async def main():
 server=serve(Path('web/dist').resolve())
 try:
  async with async_playwright() as p:
   browser=await p.webkit.launch() if '--webkit' in sys.argv else await p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,args=['--no-sandbox'])
   for width in [390,820,1440]:
    for design,theme in [('editorial','dark'),('editorial','light'),('classic','dark'),('classic','light')]:
     context=await context_for(browser,width);requests=[];errors=[]
     await context.add_init_script(f"localStorage.setItem('xyz:design',{json.dumps(design)});localStorage.setItem('xyz:color-theme',{json.dumps(theme)})")
     async def api(route):
      query=parse_qs(urlparse(route.request.url).query)
      rows=[note(n) for n in range(1,13)]
      if query.get('cursor'):rows=[note(13)]+[dict(note(n),id=f'other{n}',platform='youtube',source_url='',title=f'Independent video {n}') for n in range(1,12)]
      await route.fulfill(json={'items':rows,'next_cursor':None if query.get('cursor') else 'next'})
     await context.route('**/api/library?**',api)
     page=await context.new_page();page.on('request',lambda r:requests.append(r.url));page.on('pageerror',lambda e:errors.append(str(e)))
     for path in ['/','/library']:
      await page.goto(f'http://127.0.0.1:{server.server_port}'+path)
      for reload in [False,True]:
       if reload:await page.reload()
       await page.locator('.series-card').wait_for()
       await page.get_by_text('Independent video 1',exact=True).wait_for()
       await page.wait_for_timeout(150)
       assert await page.locator('.series-card').count()==1
       assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
       assert not any('/assets/workspace-' in url and '.css' in url for url in requests),requests
       if design=='editorial':
        for selector in (['#dashboard-add-content','.dashboard-recent-filters button[aria-pressed=true]'] if path=='/' else ['.library-card']):
         assert await page.locator(selector).first.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgba(0, 0, 0, 0)',(path,selector)
        assert await page.locator('.series-card').evaluate("e=>getComputedStyle(e).borderRadius")=='0px'
       if path=='/library':
        await page.get_by_role('button',name='list layout',exact=True).click()
        await page.locator('.library-card').first.hover()
        if design=='editorial':assert await page.locator('.library-card').first.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgba(0, 0, 0, 0)'
      await page.screenshot(path=f'/tmp/series-fixed-{design}-{theme}-{width}-'+('home' if path=='/' else 'library')+'.png',full_page=True)
      # Optional chunks remain safe after a skin switch and switching back.
      await choose(page,'classic' if design=='editorial' else 'editorial',theme)
      await choose(page,design,theme)
      await page.wait_for_timeout(200)
      if design=='editorial' and path=='/library':assert await page.locator('.library-card').first.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgba(0, 0, 0, 0)'
     assert not errors,errors
     print(json.dumps({'width':width,'design':design,'theme':theme,'cold_start_reload_mix_pagination':'passed'}),flush=True)
     await context.close()
   await browser.close()
 finally:server.shutdown()
if __name__=='__main__':asyncio.run(main())
