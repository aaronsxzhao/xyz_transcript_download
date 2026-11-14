"""A delayed or failed font manifest must not gate the selected Editorial skin."""
import argparse
import asyncio
import functools
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_network_resilience import NetworkPreview, PreviewServer
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

class FontPreview(NetworkPreview):
    def do_GET(self):
        path=urlparse(self.path).path
        file=Path(self.translate_path(path))
        if path.startswith('/assets/editorial-') and path.endswith('.css') and file.is_file() and b'@font-face' in file.read_bytes():
            if self.state['font_fail']:
                self.send_response(503);self.send_header('Content-Length','0');self.end_headers();return
            self.state['font_release'].wait(30)
        super().do_GET()

async def check(browser,dist,label,output):
    state={'reads':[],'asset_delay':0,'document_delay':0,'release':False,'font_release':threading.Event(),'font_fail':False}
    handler=type('Handler',(FontPreview,),{'state':state})
    server=PreviewServer(('127.0.0.1',0),functools.partial(handler,directory=str(dist),bootstrap=True))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    context=await browser.new_context(viewport={'width':390,'height':900},service_workers='block')
    await context.add_init_script("localStorage.setItem('xyz:design','editorial');localStorage.setItem('xyz:color-theme','light')")
    page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(e.name))
    report={'label':label}
    try:
        start=time.monotonic();await page.goto(origin+'/login',wait_until='commit')
        email=page.get_by_label('Email',exact=True);opened=False
        try:await email.wait_for(timeout=2500);opened=True
        except BrowserTimeout:pass
        report.update(opens_before_font_manifest=opened,usable_ms=round((time.monotonic()-start)*1000))
        if label.startswith('after'):
            assert opened and await page.locator('html').get_attribute('data-design')=='editorial',report
            assert await page.locator('[data-editorial-fonts]').get_attribute('rel')=='preload'
            await email.fill('font-swap@example.invalid')
            await page.get_by_role('checkbox').check()
        state['font_release'].set()
        await email.wait_for(timeout=5000)
        if label.startswith('after'):
            await page.wait_for_function("document.querySelector('[data-editorial-fonts]')?.rel==='stylesheet' && !!document.querySelector('[data-editorial-fonts]').sheet",timeout=5000)
            await page.evaluate("document.fonts.load('400 16px \"Noto Serif SC\"','Email')")
            assert await page.evaluate("[...document.fonts].some(f=>f.family.includes('Noto Serif SC')&&f.status==='loaded')")
            assert await email.input_value()=='font-swap@example.invalid'
            assert await page.get_by_role('checkbox').is_checked()
            assert await page.locator('html').get_attribute('data-design')=='editorial'
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            report['font_applies_without_reset']=True
            if output:
                output.mkdir(parents=True,exist_ok=True)
                await page.screenshot(path=str(output/(label+'-fonts.png')))
            await page.close();state['font_fail']=True
            page=await context.new_page();page.on('pageerror',lambda e:errors.append(e.name))
            await page.route('**/assets/**',lambda route:route.continue_())  # Disable cache for the HTTP503 case.
            async with page.expect_response(lambda r:'/assets/editorial-fonts-' in r.url,timeout=2500) as pending:
                await page.goto(origin+'/login',wait_until='commit')
            assert (await pending.value).status==503
            await page.get_by_label('Email',exact=True).wait_for(timeout=2500)
            assert await page.locator('html').get_attribute('data-design')=='editorial'
            assert await page.locator('html').get_attribute('data-theme')=='light'
            assert not errors,errors
            report['font_503_preserves_editorial']=True
        print(json.dumps(report),flush=True)
    finally:
        state['font_release'].set();await context.close();server.shutdown()

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    async with async_playwright() as p:
        for name in ['chromium']+(['webkit'] if args.webkit else []):
            browser=await p.webkit.launch(headless=True) if name=='webkit' else await p.chromium.launch(executable_path=args.browser_path,headless=True,chromium_sandbox=True)
            try:
                if args.baseline_dist:await check(browser,args.baseline_dist,'before-'+name,args.output)
                await check(browser,Path(__file__).resolve().parents[1]/'web/dist','after-'+name,args.output)
            finally:await browser.close()
if __name__=='__main__':asyncio.run(main())
