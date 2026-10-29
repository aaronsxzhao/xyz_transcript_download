import asyncio,json,time,sys,argparse
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures,serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright
parser=argparse.ArgumentParser(description='Synthetic reader theme and interaction regression; no production data.')
parser.add_argument('--dist',default='web/dist')
parser.add_argument('--output',default='/tmp/reader-theme-check')
parser.add_argument('--browser-path',default=None)
parser.add_argument('--browser-args',type=Path)
args=parser.parse_args()
async def main():
 server=serve(Path(args.dist).resolve());origin=f'http://127.0.0.1:{server.server_port}'
 out=Path(args.output);out.mkdir(exist_ok=True)
 results=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=args.browser_path,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
  for design,theme in [('editorial','light'),('editorial','dark'),('classic','light'),('classic','dark')]:
   for width in [390,1280]:
    ctx=await browser.new_context(viewport={'width':width,'height':844},service_workers='block')
    await ctx.add_init_script("localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+3600))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',authenticated:true}));localStorage.setItem('xyz:design',"+json.dumps(design)+");localStorage.setItem('xyz:color-theme',"+json.dumps(theme)+");window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}};")
    page=await ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    task,summary=fixtures();task['transcript']['segments']=task['transcript']['segments'][:80];task['markdown']='# Learning and memory\n\n## Practice\n\nLearning improves through regular deliberate practice.\n\n## Rest\n\nSleep supports memory.'
    async def api(route):
     path=urlparse(route.request.url).path;body={}
     if path=='/api/auth/config':body={'supabase_enabled':True}
     elif path=='/api/auth/me':body={'id':'bench','authenticated':True,'email':'fixture@example.com'}
     elif path=='/api/video-notes/tasks/bench':body=task
     elif path.endswith('/transcript'):body={'transcript':task['transcript']}
     elif path=='/api/summaries/bench':body=summary
     await route.fulfill(body=json.dumps(body),content_type='application/json')
    await page.route('**/api/**',api)
    await page.goto(origin+'/videos/bench');await page.locator('.unified-header h1').wait_for()
    await page.get_by_role('tab',name='Transcript',exact=True).click()
    await page.get_by_role('region',name='Transcript segments',exact=True).wait_for()
    await page.wait_for_timeout(400)
    colors=await page.evaluate('''()=>{const color=s=>getComputedStyle(document.querySelector(s)).color;return {title:color('.unified-header h1'),transcript:color('[aria-label="Transcript segments"] p'),toolbar:getComputedStyle(document.querySelector('.unified-toolbar')).backgroundColor}}''')
    if theme=='light':
     assert colors['title'] in ('rgb(38, 37, 33)','rgb(37, 50, 71)'),colors
     assert colors['transcript'] in ('rgb(38, 37, 33)','rgb(52, 65, 86)'),colors
    await page.screenshot(path=str(out/f'{design}-{theme}-{width}-transcript.png'))
    await page.get_by_role('button',name='Full text',exact=True).click();await page.get_by_role('region',name='Full transcript text').wait_for()
    await page.get_by_role('tab',name='Mind map',exact=True).click();await page.locator('.markmap-node').first.wait_for(timeout=25000)
    await page.wait_for_timeout(300)
    await page.get_by_role('button',name='Fit to view').click()
    await page.screenshot(path=str(out/f'{design}-{theme}-{width}-mindmap.png'))
    colors['map']=await page.locator('.mindmap-canvas svg').evaluate('(el)=>getComputedStyle(el).color')
    if theme=='light': assert colors['map'] in ('rgb(38, 37, 33)','rgb(37, 50, 71)'),colors
    assert not errors,errors
    async with page.expect_download() as info: await page.get_by_role('button',name='Export SVG').click()
    download=await info.value;await download.save_as(str(out/f'{design}-{theme}-{width}.svg'))
    await page.get_by_role('tab',name='Summary',exact=True).click();await page.get_by_role('tab',name='Mind map',exact=True).click();await page.locator('.markmap-node').first.wait_for()
    results.append({'design':design,'theme':theme,'width':width,'colors':colors,'errors':errors})
    await ctx.close()
  await browser.close()
 server.shutdown();(out/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
asyncio.run(main())
