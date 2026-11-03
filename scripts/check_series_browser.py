"""Series discovery across recent content and library, with controlled read-only APIs."""
import asyncio,json,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for,choose
from scripts.check_library_browser import serve
from playwright.async_api import async_playwright

def note(n):
 return dict(id=f'p{n}',kind='video',platform='bilibili',source_url=f'https://www.bilibili.com/video/BVseries?p={n}',title=f'斯坦福大学：如何创业 · P{n}/21 第{n}讲',source='世界课程精选站',status='completed',date='2026-11-02',thumbnail='https://i0.hdslb.com/series-cover.jpg')
async def main():
 server=serve(Path('web/dist').resolve())
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   for width in [390,820,1440]:
    for design,theme in [('classic','dark'),('classic','light'),('editorial','dark'),('editorial','light')]:
     context=await context_for(browser,width);page=await context.new_page();errors=[];writes=[];fail=[False]
     page.on('pageerror',lambda e:errors.append(str(e)))
     async def api(route):
      url=urlparse(route.request.url);query=parse_qs(url.query)
      if route.request.method!='GET':writes.append(url.path)
      if url.path=='/api/library':
       rows=[note(19)] if query.get('q') else [note(19),note(21),note(17)]
       await route.fulfill(json={'items':[note(1)] if query.get('cursor') else rows,'next_cursor':None if query.get('cursor') or query.get('q') else 'next'})
      elif '/collections/' in url.path:
       if fail[0]:await route.fulfill(status=503,json={'detail':'Unavailable'});return
       await route.fulfill(json={'parts':[dict(page=n,title=f'第{n}讲 · 创业课程',status='success' if n in [1,17,19,21] else 'not_started',task_id=f'p{n}' if n in [1,17,19,21] else None) for n in range(21,0,-1)]})
      else:await route.fallback()
     await context.route('**/api/**',api)
     await context.route('**/api/image-proxy?**',lambda route:route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#38493e"/><text x="24" y="100" fill="#f7f4e9" font-size="32">Stanford course</text></svg>'))
     for path in ['/','/library']:
      await page.goto(f'http://127.0.0.1:{server.server_port}'+path);await choose(page,design,theme)
      card=page.locator('[data-series="series:BVseries"]');await card.wait_for();await card.scroll_into_view_if_needed()
      assert await card.count()==1
      assert await card.locator('h2').inner_text()=='斯坦福大学：如何创业'
      await card.get_by_role('button',name='View episodes',exact=True).focus();await page.keyboard.press('Enter')
      await page.wait_for_function('document.querySelectorAll(".series-episodes li").length===21')
      labels=await card.locator('.series-part-number').all_text_contents();assert labels==[f'P{n}' for n in range(1,22)],labels
      assert await card.locator('a[href="/videos/p1"]').count()==1
      assert await card.get_by_role('button',name='Hide episodes').get_attribute('aria-expanded')=='true'
      await page.get_by_role('button',name='Load more' if path=='/' else 'Show more notes',exact=True).click()
      await page.wait_for_timeout(250)
      assert await card.count()==1
      if path=='/library':
       for mode in ['list','grid']:
        await page.get_by_role('button',name=f'{mode} layout',exact=True).click()
        assert await card.count()==1
      await card.scroll_into_view_if_needed();await page.wait_for_timeout(250)
      assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      await page.screenshot(path=f'/tmp/series-{design}-{theme}-{width}-{"home" if path=="/" else "library"}.png')
      fail[0]=True;await card.get_by_role('button',name='Refresh',exact=True).click();await card.get_by_role('alert').wait_for()
      assert await card.locator('a[href="/videos/p1"]').count()==1
      fail[0]=False;await card.get_by_role('button',name='Refresh',exact=True).click();await card.get_by_role('alert').wait_for(state='hidden')
     await page.get_by_role('textbox',name='Search saved notes').fill('第19讲')
     await page.wait_for_timeout(400);assert await page.locator('[data-series]').count()==1
     assert not errors,errors
     assert not [path for path in writes if path.startswith('/api/video-notes/')],writes
     print(json.dumps({'width':width,'design':design,'theme':theme,'series':1,'ordered_episodes':21,'pagination':'passed','error_retry':'passed'}),flush=True)
     await context.close()
   await browser.close()
 finally:server.shutdown()
if __name__=='__main__':asyncio.run(main())
