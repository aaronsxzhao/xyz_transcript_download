"""Cold startup must work even when every external JS/CSS request is blocked."""
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
from scripts.check_page_boundaries import DataPreview
from scripts.check_network_resilience import PreviewServer
from scripts.check_page_loading import token
from api.frontend import frontend_html
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

class StreamingPreview(DataPreview):
    def do_GET(self):
        if self.path == '/settings?stream=1':
            html=frontend_html(Path(self.directory),'settings',True,'https://example.supabase.co').encode()
            split=html.index(b'<script data-document-program')
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(html)));self.end_headers()
            self.wfile.write(html[:split]);self.wfile.flush();time.sleep(3);self.wfile.write(html[split:]);return
        super().do_GET()


async def check(browser, dist, label):
    state={'reads':[],'asset_delay':0,'document_delay':0,'release':False}
    handler=type('Handler',(StreamingPreview,),{'state':state})
    server=PreviewServer(('127.0.0.1',0),functools.partial(handler,directory=str(dist),bootstrap=True))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    context=await browser.new_context(viewport={'width':1440,'height':1000}, service_workers='block')
    await context.add_init_script("if(location.protocol==='http:'){localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+3600))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}}}")
    denied=[]
    async def assets(route):
        path=urlparse(route.request.url).path
        if path.endswith(('.js','.css')):
            denied.append(path);return await route.fulfill(status=503,body='Synthetic blocked file',content_type='application/javascript' if path.endswith('.js') else 'text/css')
        await route.continue_()
    await context.route('**/assets/**',assets)
    results={'label':label}
    try:
        for name,path,selector in [('settings','/settings','select[aria-label="Summary provider"]'),('podcasts','/podcasts','main h1'),('summary','/viewer/699acfb5de29766da924dee1','text=Readable podcast overview.'),('local','/videos/local-completed','article')]:
            page=await context.new_page();errors=[];console_errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)[:300]))
            page.on('console',lambda message:console_errors.append(message.text[:300]) if message.type=='error' else None)
            started=time.monotonic()
            await page.goto(origin+path,wait_until='commit')
            opened=False
            try:
                await page.wait_for_function("!document.querySelector('#startup-shell')",timeout=2500)
                await page.locator(selector).first.wait_for(timeout=2500);opened=True
            except BrowserTimeout:pass
            results[name]={'opens':opened,'milliseconds':round((time.monotonic()-started)*1000)}
            if label.startswith('after'):
                assert opened,{'results':results,'errors':errors,'console_errors':console_errors,'importmaps':await page.locator('script[type=importmap]').count(),'entry':await page.locator('[data-entry]').count()}
                assert not errors,errors
                if name=='settings':
                    await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]').disabled")
                    assert not denied,denied
                    await page.get_by_role('link',name='Library',exact=True).click()
                    await page.locator('input[aria-label="Search saved notes"]').wait_for(timeout=2000)
                    results['navigation_interactive']=True
                if name=='local':
                    await page.wait_for_function("Array.from(document.querySelectorAll('article img')).some(image=>image.naturalWidth>0)",timeout=3000)
                    results['screenshots_without_external_js']=True
            await page.close()
        if label.startswith('after'):
            page=await context.new_page();before=state['reads'].count('/api/settings');started=time.monotonic()
            await page.goto(origin+'/settings?stream=1',wait_until='commit')
            await page.locator('#startup-shell nav').wait_for(timeout=1500)
            results['streamed_navigation_ms']=round((time.monotonic()-started)*1000)
            await page.wait_for_timeout(350)
            assert state['reads'].count('/api/settings')==before+1
            assert await page.locator('[data-document-program]').count()==0
            results['early_settings_before_program']=True
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=5000)
            results['streamed_program_ready_ms']=round((time.monotonic()-started)*1000)
            assert state['reads'].count('/api/settings')==before+1
            await page.close()
            # Exercise the watchdog without any framework ever executing.
            page=await context.new_page();await page.clock.install()
            raw=(Path(__file__).resolve().parents[1]/'web/index.html').read_text()
            raw=raw.replace('<!-- xyz-startup -->','<script>'+(Path(__file__).resolve().parents[1]/'web/src/startup.js').read_text()+'</script>')
            raw=raw.replace('<script type="module" src="/src/main.tsx"></script>','')
            await page.route('**/podcasts?probe=private-value',lambda route:route.fulfill(body=raw,content_type='text/html'))
            await page.route('**/api/performance',lambda route:route.fulfill(status=204))
            await page.goto(origin+'/podcasts?probe=private-value',wait_until='domcontentloaded')
            async with page.expect_request(lambda request:urlparse(request.url).path=='/api/performance',timeout=3000) as pending:
                await page.clock.fast_forward(13000)
            payload=(await pending.value).post_data_json
            assert payload['stage']=='bootstrap' and payload['outcome']=='slow' and payload['page']=='podcasts'
            assert payload['program_embedded'] is False
            assert 'private-value' not in json.dumps(payload) and 'url' not in payload
            results['pre_framework_failure_recorded']=True
            await page.close()
        results['external_requests_denied']=len(denied)
        print(json.dumps(results),flush=True)
    finally:
        await context.close();server.shutdown()

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);parser.add_argument('--webkit',action='store_true');args=parser.parse_args()
    current=Path(__file__).resolve().parents[1]/'web/dist'
    async with async_playwright() as p:
        for label,dist in [('before',args.baseline_dist),('after',current)]:
            if not dist:continue
            browser=await p.chromium.launch(executable_path=args.browser_path,headless=True,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
            await check(browser,dist,label);await browser.close()
        if args.webkit:
            browser=await p.webkit.launch(headless=True);await check(browser,current,'after-webkit');await browser.close()
if __name__=='__main__':asyncio.run(main())
