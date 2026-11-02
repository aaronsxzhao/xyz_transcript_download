"""Both list types expose the same summary-only and whole-item deletion choices."""
import asyncio,sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for,choose
from scripts.check_library_browser import serve,fixtures
from playwright.async_api import async_playwright

async def main():
 server=serve(Path('web/dist').resolve())
 try:
  async with async_playwright() as p:
   browser=await p.webkit.launch() if '--webkit' in sys.argv else await p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,args=['--no-sandbox'])
   for width in [390,1280]:
    for kind in ['episode','video']:
     context=await context_for(browser,width,touch=True)
     task,_=fixtures();task.update(channel='Fixture',updated_at='2026-11-01T00:00:00Z')
     episode={'eid':'bench','pid':'show','title':'Synthetic episode','has_summary':True,'has_transcript':True,'duration':1200}
     removed=False;calls=[]
     async def api(route):
      nonlocal removed
      path=urlparse(route.request.url).path
      if route.request.method=='DELETE':
       calls.append(path)
       if path=='/api/summaries/bench':episode['has_summary']=False
       elif path=='/api/video-notes/tasks/bench/summary':task.update(status='discovered',markdown='',versions=[],progress=0,updated_at='2026-11-02T00:00:00Z')
       else:removed=True
       await route.fulfill(json={'message':'Deleted'})
      elif path=='/api/video-notes/tasks/by-channel':await route.fulfill(json={'tasks':[] if removed else [task],'next_cursor':None})
      elif path=='/api/video-notes/tasks/bench':await route.fulfill(json=task)
      elif path=='/api/podcasts/content':await route.fulfill(json=[] if removed else [episode])
      else:await route.fallback()
     await context.route('**/api/**',api)
     page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     url='/podcasts/show/episodes' if kind=='episode' else '/videos?platform=youtube&channel=Fixture'
     await page.goto(f'http://127.0.0.1:{server.server_port}'+url)
     title=episode['title'] if kind=='episode' else task['title']
     for design in ['classic','editorial']:
      await choose(page,design,'dark' if design=='classic' else 'light')
      menu=page.get_by_label('More actions for '+title,exact=True)
      await menu.click()
      await page.get_by_role('button',name='Delete summary only',exact=True).wait_for()
      assert await page.get_by_role('button',name='Delete '+kind,exact=True).is_visible()
      assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
      await menu.press('Escape')
     await menu.click()
     async with page.expect_event('dialog') as dialog:
      await page.get_by_role('button',name='Delete summary only',exact=True).click()
     await (await dialog.value).dismiss()
     await page.wait_for_function("[...document.querySelectorAll('button')].some(b=>b.textContent==='Delete summary only'&&!b.disabled)")
     assert not calls
     async with page.expect_event('dialog') as dialog:
      await page.get_by_role('button',name='Delete summary only',exact=True).click()
     await (await dialog.value).accept()
     await page.wait_for_function("[...document.querySelectorAll('button')].some(b=>b.textContent==='Delete summary only'&&b.disabled)")
     await page.get_by_role('button',name='Process',exact=True).wait_for()
     assert calls==(['/api/summaries/bench'] if kind=='episode' else ['/api/video-notes/tasks/bench/summary'])
     assert await page.get_by_role('heading',name=title,exact=True).count()==1
     assert episode['has_transcript'] and task['transcript']
     await page.reload()
     await page.get_by_label('More actions for '+title,exact=True).click()
     assert await page.get_by_role('button',name='Delete summary only',exact=True).is_disabled()
     page.once('dialog',lambda d:d.accept())
     await page.get_by_role('button',name='Delete '+kind,exact=True).click()
     await page.get_by_role('heading',name=title,exact=True).wait_for(state='detached')
     assert len(calls)==2 and removed
     assert not errors,errors
     print(f'{width} {kind}: cancel, summary-only, retain source, reload, full deletion passed',flush=True)
     await context.close()
   await browser.close()
 finally:server.shutdown()

if __name__=='__main__':asyncio.run(main())
