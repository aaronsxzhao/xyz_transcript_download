"""Synthetic browser checks for slow navigation, public caching and release rollback."""
import argparse
import asyncio
import functools
import json
import re
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_page_loading import Preview, token
from playwright.async_api import async_playwright


class NetworkPreview(Preview):
    state = None
    def do_GET(self):
        if self.state.get('rollback_dist'):
            self.directory = str(self.state['rollback_dist'])
        path = urlparse(self.path).path
        self.state['reads'].append(path)
        if path.startswith('/api/'):
            time.sleep(.15)
            data = {'/api/auth/me':{'id':'bench','email':'bench@example.com','authenticated':True},
                    '/api/settings':{'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq','llm_model':'openai/gpt-oss-120b','check_interval':3600},
                    '/api/library/sources':{'sources':[],'next_cursor':None},
                    '/api/library':{'items':[],'next_cursor':None}, '/api/performance':{'pages':{'library':{'samples':12,'p50_ms':450,'p95_ms':1200,'slow_count':0,'error_count':0}}}, '/api/podcasts':[], '/api/summaries':[], '/api/video-notes/tasks':{'tasks':[]},
                    '/api/video-notes/progress':{'tasks':[]}, '/api/jobs':{'jobs':[]},
                    '/api/video-notes/channels':{'channels':[]}, '/api/cookies':{'cookies':[]}}
            payload = json.dumps(data.get(path, {})).encode()
            self.send_response(200); self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            return
        if path.startswith('/assets/'):
            time.sleep(self.state['asset_delay'])
        if path=='/sw.js' and self.state['release']:
            source=(Path(self.directory)/'sw.js').read_text()
            source=re.sub(r"const VERSION = '[^']+';", "const VERSION = 'integration-next';",source)
            body=source.encode();self.send_response(200);self.send_header('Content-Type','application/javascript');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if not path.startswith('/assets/') and path!='/sw.js':
            time.sleep(self.state['document_delay'])
        super().do_GET()


class PreviewServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return  # Expected when the test closes a tab with a background read.
        super().handle_error(request, client_address)


async def check(browser, dist, label, rollback_dist=None):
    state={'reads':[],'asset_delay':1,'document_delay':0,'release':False}
    handler=type('Handler',(NetworkPreview,),{'state':state})
    server=PreviewServer(('127.0.0.1',0),functools.partial(handler,directory=str(dist),bootstrap=True))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}'
    context=await browser.new_context(viewport={'width':1440,'height':1000}, service_workers='allow' if label=='after' else 'block')
    await context.add_init_script("window.workerVersion=()=>new Promise(resolve=>{const channel=new MessageChannel();channel.port1.onmessage=e=>resolve(e.data);navigator.serviceWorker.controller.postMessage({type:'xyz:version'},[channel.port2]);setTimeout(()=>resolve(null),750)})")
    await context.add_init_script("if(location.protocol==='http:'){localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+3600))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}};}")
    page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        start=time.monotonic()
        await page.goto(origin+'/settings',wait_until='domcontentloaded')
        await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=20000)
        await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]').disabled")
        report={'label':label,'settings_usable_ms':round((time.monotonic()-start)*1000),'initial_program_requests':len([path for path in state['reads'] if path.startswith('/assets/')])}
        if label=='after':
            async def settings_write(route):
                if route.request.method == 'POST': await route.fulfill(status=200,content_type='application/json',body='{}')
                else: await route.continue_()
            await page.route('**/api/settings',settings_write)
            await page.get_by_label('Summary provider',exact=True).select_option('server')
            await page.get_by_text('Unsaved changes',exact=True).wait_for()
            page.once('dialog',lambda dialog: asyncio.create_task(dialog.dismiss()))
            await page.get_by_role('link',name='Library',exact=True).click()
            assert '/settings' in page.url
            await page.get_by_role('button',name='Save Settings',exact=True).click()
            await page.get_by_text('All changes saved',exact=True).wait_for()
            await page.screenshot(path='/tmp/xyz-settings-review.png')
            await page.set_viewport_size({'width':390,'height':960})
            await page.screenshot(path='/tmp/xyz-settings-mobile-review.png')
            assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
            save_bounds = await page.get_by_role('button',name='Save Settings',exact=True).bounding_box()
            assert save_bounds['height'] >= 44
            await page.set_viewport_size({'width':1440,'height':1000})
            report['settings_unsaved_guard_and_save']=True
            await page.get_by_role('button',name='Tools & Data',exact=True).click()
            await page.get_by_role('button',name='Show recent timings',exact=True).click()
            await page.get_by_role('cell',name='1.20s',exact=True).wait_for()
            report['account_performance_panel']=True
        reads=len(state['reads']);start=time.monotonic()
        await page.get_by_role('link',name='Library',exact=True).click()
        await page.locator('input[aria-label="Search saved notes"]').wait_for(timeout=15000)
        report['library_navigation_ms']=round((time.monotonic()-start)*1000)
        report['library_program_requests']=len([path for path in state['reads'][reads:] if path.startswith('/assets/')])
        if label=='after':
            await page.evaluate('navigator.serviceWorker.ready')
            await page.wait_for_function('!!navigator.serviceWorker.controller',timeout=20000)
            original_version=await page.evaluate('workerVersion()')
            state['asset_delay']=0;state['document_delay']=12
            start=time.monotonic()
            await page.goto(origin+'/settings?probe=preserved#section',wait_until='domcontentloaded')
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=5000)
            report['repeat_document_and_form_ms']=round((time.monotonic()-start)*1000)
            assert report['repeat_document_and_form_ms']<2500,report
            assert page.url.endswith('/settings?probe=preserved#section'),page.url
            keys=await page.evaluate("(async()=>{const result=[];for(const key of await caches.keys())for(const request of await(await caches.open(key)).keys())result.push(new URL(request.url).pathname);return result})()")
            assert keys and all(path=='/__xyz_public_shell__' or path.startswith('/assets/') for path in keys),keys
            await context.set_offline(True)
            await page.reload(wait_until='domcontentloaded')
            assert await page.locator('header').first.is_visible()
            assert await page.evaluate("fetch('/api/settings').then(()=>false,()=>true)")
            assert await page.evaluate("fetch('/data/screenshots/private.jpg').then(()=>false,()=>true)")
            report['offline_public_shell_only']=True
            await context.set_offline(False);state['document_delay']=0
            state['release']=True
            await page.evaluate('(async()=>{const registration=await navigator.serviceWorker.getRegistration();await registration.update()})()')
            await page.wait_for_function("(async()=> (await caches.keys()).includes('xyz-public-integration-next'))()",timeout=20000)
            await page.wait_for_function("(async()=>await workerVersion()==='integration-next')()",timeout=15000)
            await page.get_by_role('button',name='Reload',exact=True).wait_for(timeout=15000)
            report['update_available_without_forced_reload']=True
            banner=page.locator('header [role=status]')
            assert await banner.is_visible()
            assert (await banner.bounding_box())['y']<100
            await page.get_by_role('button',name='Reload',exact=True).click()
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=15000)
            await page.wait_for_function("!location.search.includes('__xyz_boot')")
            assert page.url.endswith('/settings?probe=preserved#section'),page.url
            report['prominent_update_reload_preserves_route']=True
            state['release']=False
            await page.evaluate('(async()=>{const registration=await navigator.serviceWorker.getRegistration();await registration.update()})()')
            await page.wait_for_function("(async expected=>await workerVersion()===expected)", arg=original_version, timeout=15000)
            await page.reload(wait_until='domcontentloaded')
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=5000)
            assert len(await page.evaluate("caches.keys()"))<=2
            report['rollback_usable']=True
            if rollback_dist and not (rollback_dist/'sw.js').exists():
                # The actual preceding image has no worker. Its public HTML
                # must replace the shell even when worker updates are unavailable.
                state['rollback_dist']=rollback_dist
                await page.goto(origin+'/settings?rollback-check=keep',wait_until='domcontentloaded')
                await page.get_by_role('button',name='Reload',exact=True).wait_for(timeout=20000)
                await page.get_by_role('button',name='Reload',exact=True).click()
                await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=15000)
                old_entry=re.search(r'<script type="module"[^>]*src="([^"]+)"',(rollback_dist/'index.html').read_text()).group(1)
                assert await page.evaluate("entry=>performance.getEntriesByType('resource').some(resource=>new URL(resource.name).pathname===entry)",old_entry)
                assert page.url.endswith('?rollback-check=keep')
                report['rollback_to_pre_cache_image_usable']=True
        assert not errors,errors
        report['js_errors']=0
        print(json.dumps(report),flush=True)
        return report
    finally:
        await context.close();server.shutdown()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);args=parser.parse_args()
    async with async_playwright() as playwright:
        for label,dist in [('before',args.baseline_dist),('after',Path(__file__).resolve().parents[1]/'web/dist')]:
            if not dist:continue
            browser=await playwright.chromium.launch(executable_path=args.browser_path,headless=True,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
            await check(browser,dist,label,args.baseline_dist if label=='after' else None);await browser.close()
if __name__=='__main__':asyncio.run(main())
