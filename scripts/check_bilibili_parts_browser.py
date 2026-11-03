"""Multipart reader bounds, unavailable states and visible selection feedback."""
import asyncio,json,sys
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
   for design,theme in [('classic','dark'),('classic','light'),('editorial','light'),('editorial','dark')]:
    for width in [320,390,820]:
     task,_=fixtures()
     parts=[{'page':i,'title':f'【中英文双语】斯坦福大学：如何创业 · P{i}/21 第{i}讲 - 如何开始创业 '+('LongUnbrokenTitle'*12 if i==5 else ''),'url':f'https://www.bilibili.com/video/BVexample?p={i}','status':'success' if i<3 else 'transcribing' if i==3 else 'not_started','progress':0,'task_id':'bench' if i==1 else f'p{i}' if i<4 else None} for i in range(1,22)]
     task.update(thumbnail='https://i0.hdslb.com/bfs/archive/fixture.jpg',platform='bilibili',title=parts[0]['title'],source_metadata={'bilibili_part':parts[0],'bilibili_parts':parts},markdown='# Stanford course\n\n## Course notes\n\nA stable reading column with a multipart selection list.')
     task['markdown'] += '\n\n' + 'https://example.com/' + 'longpath'*80 + '\n\n```text\n' + 'longcode'*100 + '\n```\n\n| Column | Long value |\n| --- | --- |\n| Test | ' + 'LongCell'*80 + ' |\n\n$$\n' + ' + '.join(['x_i']*80) + '\n$$'
     context=await context_for(browser,width,touch=True)
     async def api(route):
      path=urlparse(route.request.url).path
      if path == '/api/image-proxy':
       await route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#524331"/><text x="30" y="100" font-size="25" fill="white">Stanford course</text></svg>')
      elif path in ['/api/video-notes/tasks/bench','/api/video-notes/tasks/p2']:
       current={**task,'id':path.rsplit('/',1)[-1]};current['title']=task['title']+(' · P2' if current['id']=='p2' else '');current['source_metadata']={**task['source_metadata'],'bilibili_part':parts[1] if current['id']=='p2' else parts[0]};await route.fulfill(json=current)
      elif path == '/api/video-notes/tasks/by-channel':await route.fulfill(json={'tasks':[{**{key:value for key,value in task.items() if key not in {'transcript','markdown','versions'}},'id':f'part-{part["page"]}','url':'https://b23.tv/legacy' if part['page']==1 else part['url'],'title':part['title'],'status':part['status'],'channel':'Stanford','source_metadata':{'bilibili_part':part,'bilibili_parts':parts}} for part in reversed(parts)]+[{**task,'id':'standalone','url':'https://www.bilibili.com/video/BVstandalone','title':'普通视频 · Standalone video','source_metadata':{},'channel':'Stanford'}],'next_cursor':None})
      elif path in ['/api/video-notes/collections/bench/parts','/api/video-notes/collections/p2/parts']:await route.fulfill(json={'parts':parts})
      else:await route.fallback()
     await context.route('**/api/**',api)
     page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     await page.goto(f'http://127.0.0.1:{server.server_port}/videos/bench')
     await choose(page,design,theme)
     panel=page.get_by_role('region',name='Bilibili collection parts')
     await panel.locator('.bilibili-part-row').last.wait_for(state='attached')
     assert not await panel.locator('.bilibili-directory').evaluate('e=>e.open')
     toggle=panel.locator('.bilibili-directory > summary')
     await toggle.click()
     assert await panel.locator('.bilibili-directory').evaluate('e=>e.open')
     await toggle.click()
     assert not await panel.locator('.bilibili-directory').evaluate('e=>e.open')
     await toggle.press('Enter')
     assert await panel.locator('.bilibili-directory').evaluate('e=>e.open')
     for i in [0,1,2]:
      assert await panel.locator('.bilibili-part-row').nth(i).get_attribute('data-unavailable')=='true'
      assert await panel.locator('input').nth(i).is_disabled()
     action=panel.get_by_role('button',name='Process selected (0)',exact=True)
     before_color=await action.evaluate('e=>getComputedStyle(e).backgroundColor')
     await panel.locator('input').nth(4).check()
     selected=panel.locator('.bilibili-part-row').nth(4)
     assert await selected.get_attribute('data-selected')=='true'
     action=panel.get_by_role('button',name='Process selected (1)',exact=True)
     assert await action.is_enabled()
     await page.wait_for_function("before=>getComputedStyle(document.querySelector('.bilibili-parts .ui-button-primary')).backgroundColor!==before",arg=before_color)
     assert await selected.evaluate('e=>getComputedStyle(e).boxShadow')!='none'
     await page.locator('.katex-display').wait_for()
     await page.screenshot(path=f'/tmp/parts-overflow-{design}-{theme}-{width}.png')
     geometry=await page.evaluate('''()=>{
      const panel=document.querySelector('.bilibili-parts'),list=document.querySelector('.bilibili-parts-list'),doc=document.querySelector('.unified-document');
      const left=doc.getBoundingClientRect().left;
      list.scrollLeft=500;window.scrollTo(500,window.scrollY);
      return {page:document.documentElement.scrollWidth<=innerWidth+1,main:[...document.querySelectorAll('main')].every(e=>e.scrollWidth<=e.clientWidth+1),panel:panel.scrollWidth<=panel.clientWidth+1,list:list.scrollWidth<=list.clientWidth+1,stable:Math.abs(doc.getBoundingClientRect().left-left)<1&&window.scrollX===0};
     }''')
     assert all(geometry.values()),(design,theme,width,geometry)
     for selector in ['.markdown-table','.summary-code','.katex-display']:
      if selector=='.markdown-table' and width>=480:continue
      scroller=page.locator(selector).first
      assert await scroller.evaluate('e=>{e.scrollLeft=100;return e.scrollWidth>e.clientWidth&&e.scrollLeft>0}'),selector
     await panel.get_by_role('navigation',name='Part navigation').get_by_role('link',name='Next').click()
     await page.wait_for_url('**/videos/p2')
     await page.get_by_role('heading',name=task['title']+' · P2',exact=True).wait_for()
     await panel.locator('.bilibili-part-row').last.wait_for(state='attached')
     await page.locator('.katex-display').wait_for()
     assert await page.evaluate('()=>{const m=document.querySelector("main");m.scrollLeft=100;return m.scrollWidth<=m.clientWidth+1&&m.scrollLeft===0}'), 'Part navigation shifted the reading page'
     if not await panel.locator('.bilibili-directory').evaluate('e=>e.open'):await panel.locator('.bilibili-directory > summary').click()
     await panel.scroll_into_view_if_needed()
     if width==390:await page.screenshot(path=f'/tmp/bilibili-parts-{design}-{theme}.png')
     await page.goto(f'http://127.0.0.1:{server.server_port}/videos?platform=bilibili&channel=Stanford')
     collection=page.locator('.video-collection')
     try:await collection.wait_for()
     except Exception:
      await page.screenshot(path='/tmp/collection-failure.png');print(await page.locator('body').inner_text(),errors,flush=True);raise
     assert await collection.count()==1
     assert not await collection.evaluate('e=>e.open')
     styles=await page.evaluate("""()=>{
      const series=document.querySelector('.video-collection'),single=document.querySelector('.video-task-list > div');
      const style=(e,props)=>Object.fromEntries(props.map(p=>[p,getComputedStyle(e)[p]]));
      const props=['borderTopWidth','borderTopColor','borderRadius','backgroundColor','paddingTop','paddingLeft'];
      const cover=e=>style(e.querySelector('.video-thumbnail'),['width','height','borderRadius']);
      const title=e=>style(e,['fontSize','fontFamily','fontWeight','lineHeight']);
      return {series:style(series,props),single:style(single,props),seriesCover:cover(series),singleCover:cover(single),seriesTitle:title(series.querySelector('strong')),singleTitle:title(single.querySelector('h3'))};
     }""")
     assert styles['series']==styles['single'],styles
     assert styles['seriesCover']==styles['singleCover'],styles
     assert styles['seriesTitle']==styles['singleTitle'],styles
     if width==390:await page.screenshot(path=f'/tmp/bilibili-cards-{design}-{theme}.png')
     await collection.locator(':scope > summary').click()
     titles=await collection.locator('h3').all_text_contents()
     assert len(titles)==21 and titles[0].startswith('P1 ·') and titles[9].startswith('P10 ·'),titles
     assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
     if width==390:await page.screenshot(path=f'/tmp/bilibili-collection-{design}-{theme}.png')
     assert not errors,errors
     print(json.dumps({'design':design,'theme':theme,'width':width,**geometry,'selection_feedback':True}),flush=True)
     await context.close()
   await browser.close()
 finally:server.shutdown()
if __name__=='__main__':asyncio.run(main())
