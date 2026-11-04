"""Matched-title geometry: series rows must not gain space from nested disclosure controls."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for
from scripts.check_library_browser import serve, fixtures
from scripts.check_series_browser import note
from playwright.async_api import async_playwright

async def main():
 server=serve(Path('web/dist').resolve()); output=Path('/tmp/series-spacing-'+('before' if '--record' in sys.argv else 'after'));output.mkdir(exist_ok=True)
 results=[]
 try:
  async with async_playwright() as p:
   browser=await p.webkit.launch() if '--webkit' in sys.argv else await p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,args=['--no-sandbox'])
   for width in [390,820,1440]:
    for design in ['classic','editorial']:
     for theme in ['light','dark']:
      context=await context_for(browser,width)
      await context.add_init_script(f"localStorage.setItem('xyz:design','{design}');localStorage.setItem('xyz:color-theme','{theme}')")
      title='Stanford course'
      rows=[dict(note(1),title=title+' · P1/21 Episode one'),dict(note(2),title=title+' · P2/21 Episode two'),dict(note(1),id='single',source_url='',title=title,platform='youtube')]
      await context.route('**/api/library?**',lambda r:r.fulfill(json={'items':rows,'next_cursor':None}))
      task,_=fixtures();task['platform']='bilibili'
      parts=[dict(page=n,title=title+f' · P{n}/21 Episode {n}',url=f'https://www.bilibili.com/video/BVseries?p={n}') for n in [1,2]]
      tasks=[dict(task,id=f'p{part["page"]}',title=part['title'],url=part['url'],thumbnail=rows[0]['thumbnail'],channel='Stanford',source_metadata={'bilibili_part':part,'bilibili_parts':parts}) for part in parts]
      tasks.append(dict(task,id='single',title=title,url='https://www.bilibili.com/video/BVsingle',thumbnail=rows[0]['thumbnail'],channel='Stanford',source_metadata={}))
      await context.route('**/api/video-notes/tasks/by-channel?**',lambda r:r.fulfill(json={'tasks':tasks,'next_cursor':None}))
      page=await context.new_page()
      for path in ['/','/library']:
       await page.goto(f'http://127.0.0.1:{server.server_port}'+path)
       await page.locator('.series-card').wait_for()
       if path=='/library':await page.get_by_role('button',name='list layout',exact=True).click()
       await page.wait_for_timeout(200)
       geometry=await page.evaluate('''()=>{
        const series=document.querySelector('.series-card-heading'),single=document.querySelector('a'+(location.pathname=='/'?'.reading-history-card':'.library-card'));
        return [series,single].map(e=>{const r=e.getBoundingClientRect(),footer=e.querySelector('.series-footer,.library-card-footer,.note-card-copy>p:last-child');return {height:r.height,footerHeight:footer.getBoundingClientRect().height,footerY:footer.getBoundingClientRect().y-r.y}});
       }''')
       await page.locator('.series-card').scroll_into_view_if_needed()
       await page.screenshot(path=str(output / f"{design}-{theme}-{width}-{'home' if path=='/' else 'library'}.png"))
       result=dict(width=width,design=design,theme=theme,path=path,geometry=geometry);results.append(result);print(json.dumps(result),flush=True)
       if '--record' not in sys.argv:
        assert abs(geometry[0]['height']-geometry[1]['height'])<=2,result
        assert abs(geometry[0]['footerY']-geometry[1]['footerY'])<=2,result
        toggle=page.locator('.series-toggle')
        assert await toggle.evaluate('e=>e.getBoundingClientRect().height')>=44
        await toggle.focus();await page.keyboard.press('Enter')
        assert await toggle.get_attribute('aria-expanded')=='true'
        await page.keyboard.press('Enter')
        assert await toggle.get_attribute('aria-expanded')=='false'
      await page.goto(f'http://127.0.0.1:{server.server_port}/videos?platform=bilibili&channel=Stanford')
      await page.locator('.video-collection').wait_for()
      await page.wait_for_timeout(200)
      geometry=await page.evaluate("""()=>[document.querySelector('.video-collection'),document.querySelector('.video-task-list>div')].map(e=>({height:e.getBoundingClientRect().height}))""")
      await page.screenshot(path=str(output/f'{design}-{theme}-{width}-videos.png'),full_page=True)
      result=dict(width=width,design=design,theme=theme,path='/videos',geometry=geometry);results.append(result);print(json.dumps(result),flush=True)
      if '--record' not in sys.argv:
       assert abs(geometry[0]['height']-geometry[1]['height'])<=2,result
       disclosure=page.locator('.video-collection > summary')
       await disclosure.focus();await page.keyboard.press('Enter')
       assert await page.locator('.video-collection').evaluate('e=>e.open')
       await page.keyboard.press('Enter')
       assert not await page.locator('.video-collection').evaluate('e=>e.open')
      await context.close()
   await browser.close()
 finally:
  (output/'results.json').write_text(json.dumps(results,indent=2));server.shutdown()
if __name__=='__main__':asyncio.run(main())
