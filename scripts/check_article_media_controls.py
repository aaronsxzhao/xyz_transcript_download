"""Native article media bounds and deferred audio controls; synthetic resources only."""
import asyncio, argparse, io, json, sys, wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for
from scripts.check_library_browser import serve, fixtures
from playwright.async_api import async_playwright

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--output',type=Path,default=Path('/tmp/article-media-controls'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 audio=io.BytesIO()
 with wave.open(audio,'wb') as wav:
  wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\0' * 16000)
 server=serve(Path(__file__).resolve().parents[1]/'web/dist')
 try:
  async with async_playwright() as p:
   browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
   for width in [390,820,1440]:
    for design in ['classic','editorial']:
     for theme in ['light','dark']:
      context=await context_for(browser,width);await context.add_init_script(f"localStorage.setItem('xyz:design','{design}');localStorage.setItem('xyz:color-theme','{theme}')")
      task,_=fixtures();task.update(id='article',platform='web',style='original',title='Article media controls',error='',source_metadata={'type':'article'},markdown='# Article media controls\n\n[Audio recording](https://example.com/demo.wav)\n\n[Unavailable recording](https://example.com/unavailable.wav)\n\n[Video demonstration](https://example.com/demo.mp4)')
      reads=[]
      async def media(route):
       reads.append(route.request.url)
       if route.request.url.endswith('/demo.wav'):await route.fulfill(content_type='audio/wav',body=audio.getvalue())
       else:await route.fulfill(status=404,body='Not found')
      await context.route('https://example.com/**',media)
      await context.route('**/api/video-notes/tasks/article**',lambda r:r.fulfill(json=task))
      page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      await page.goto(f'http://127.0.0.1:{server.server_port}/videos/article');players=page.locator('.article-native-media audio');await players.first.wait_for(state='attached');await page.wait_for_timeout(150)
      await page.screenshot(path=str(args.output/f'{design}-{theme}-{width}-initial.png'),full_page=True)
      geometry=await players.evaluate_all('(els)=>els.map(e=>({height:e.getBoundingClientRect().height,width:e.getBoundingClientRect().width,controls:e.controls,preload:e.preload}))')
      assert len(geometry)==2 and all(v['height']>=32 and v['width']>200 and v['controls'] and v['preload']=='none' for v in geometry),geometry
      assert not any(url.endswith('.wav') for url in reads),reads
      await players.first.focus();assert await players.first.evaluate('e=>document.activeElement===e')
      await players.first.evaluate('e=>e.load()');await page.wait_for_function("document.querySelector('audio').readyState>=1")
      assert await players.first.evaluate('e=>e.getBoundingClientRect().height')>=32
      await players.nth(1).evaluate('e=>e.load()');await players.nth(1).locator('..').get_by_role('status').wait_for()
      assert await players.nth(1).evaluate('e=>e.getBoundingClientRect().height')>=32
      assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      await page.screenshot(path=str(args.output/f'{design}-{theme}-{width}-loaded-error.png'),full_page=True)
      assert not errors,errors
      print(json.dumps(dict(width=width,design=design,theme=theme,visible_controls=True,deferred_audio=True,metadata_and_error=True)),flush=True)
      await context.close()
   await browser.close()
 finally:server.shutdown()
if __name__=='__main__':asyncio.run(main())
