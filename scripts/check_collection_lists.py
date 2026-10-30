"""Stress collection rows with long text across widths and all appearances."""
import argparse,asyncio,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.check_appearance import context_for,choose
from scripts.check_library_browser import serve
from playwright.async_api import async_playwright
async def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output',type=Path,default=Path('appearance-checks/collection-lists'))
 parser.add_argument('--browser-path')
 parser.add_argument('--webkit',action='store_true')
 args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
 server=serve(ROOT/'web/dist')
 async with async_playwright() as p:
  browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
  c=await context_for(browser,820)
  title='VeryLongUnbrokenTitleWithoutSpaces'*10
  shows=[dict(pid='show',title=title,author=title,description='Long description '*30,platform='xiaoyuzhou',episode_count=30,summarized_count=10)]
  await c.route('**/api/podcasts?*',lambda r:r.fulfill(json=shows))
  await c.route('**/api/podcasts/content?*',lambda r:r.fulfill(json=[dict(eid='bench',pid='show',title=title,duration=1200,has_summary=True,has_transcript=True,topics_count=2,key_points_count=5)]))
  await c.route('**/api/video-notes/channels',lambda r:r.fulfill(json={'channels':[dict(channel=title,platform='youtube',total=20,done=10,channel_url='https://example.test/channel')]}))
  page=await c.new_page();errors=[]
  page.on("pageerror",lambda error:errors.append(str(error)))
  for name,path in [('podcasts','/podcasts?platform=xiaoyuzhou'),('episodes','/podcasts/show/episodes'),('channels','/videos?platform=youtube')]:
   await page.goto(f'http://127.0.0.1:{server.server_port}'+path)
   await page.locator('h3').first.wait_for()
   for design,theme in [('classic','dark'),('classic','light'),('editorial','light'),('editorial','dark')]:
    await choose(page,design,theme)
    for width in [320,390,640,820,1024,1440]:
     await page.set_viewport_size({'width':width,'height':1000});await page.wait_for_timeout(250)
     overflow=await page.evaluate('document.documentElement.scrollWidth>innerWidth+1||[...document.querySelectorAll("main")].some(e=>e.scrollWidth>e.clientWidth+1)')
     print(name,design,theme,width,'overflow',overflow,flush=True)
     assert not overflow,(name,design,theme,width)
     rows=await page.locator('.collection-row').evaluate_all("""rows=>rows.map(row=>{
       const h=row.querySelector('h3'),a=row.querySelector('.collection-actions'),r=row.getBoundingClientRect(),b=a.getBoundingClientRect();
       return {right:Math.abs(r.right-b.right),title:h.getBoundingClientRect().height,line:parseFloat(getComputedStyle(h).lineHeight),buttons:[...a.children].map(e=>e.getBoundingClientRect().height),clamped:[...row.querySelectorAll('p')].filter(e=>getComputedStyle(e).webkitLineClamp==='2').every(e=>e.getBoundingClientRect().height<=parseFloat(getComputedStyle(e).lineHeight)*2+1)};
     })""")
     assert rows and all(r['right']<2 and r['title']<=r['line']*2+1 and min(r['buttons'])>=36 and r['clamped'] for r in rows),rows
     if width in [390,820]: await page.screenshot(path=str(out/f'{name}-{design}-{theme}-{width}.png'))
   if name in ['podcasts','channels']:
    search=page.get_by_placeholder('Search '+name+'...')
    await search.fill('definitely-no-matching-item')
    await page.get_by_text('No matching podcasts' if name=='podcasts' else 'No channels found',exact=True).wait_for()
    await search.fill('')
    await page.locator('.collection-row').first.wait_for()
   assert not errors,errors
  await browser.close()
 server.shutdown()
if __name__=='__main__':
 asyncio.run(main())
