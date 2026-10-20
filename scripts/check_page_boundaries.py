"""Reported pages must open even when optional JS or stylesheet requests fail."""
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
from scripts.check_page_loading import token
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout


class DataPreview(NetworkPreview):
    def do_GET(self):
        path=urlparse(self.path).path
        body=None
        if path=='/api/summaries/699acfb5de29766da924dee1':
            body={'episode_id':'699acfb5de29766da924dee1','title':'Reported podcast fixture','overview':'Readable podcast overview.','topics':['Review'],'takeaways':[],'key_points':[]}
        if path in {'/api/video-notes/tasks/bc2c988b-2b4','/api/video-notes/tasks/local-completed'}:
            local=path.endswith('local-completed')
            body={'id':path.rsplit('/',1)[1],'title':'Completed local video' if local else 'Reported video fixture','status':'success','platform':'local' if local else 'youtube','markdown':'# Readable completed note\n\nSaved content is available.\n\n![Chart](/data/screenshots/test.svg)','transcript':None,'versions':[],'formats':['summary','screenshot'],'progress':100}
        if path=='/data/screenshots/test.svg':
            data=b'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="green"/></svg>'
            self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if body is None:return super().do_GET()
        self.state['reads'].append(path)
        data=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


def core_files(dist):
    manifest=json.loads((dist/'manifest.json').read_text());seen=set();files=set()
    def visit(key):
        if key in seen:return
        seen.add(key);entry=manifest.get(key,{})
        if entry.get('file'):files.add('/'+entry['file'])
        for child in entry.get('imports',[]):visit(child)
    visit('index.html');return files


async def check(browser,dist,label):
    state={'reads':[],'asset_delay':0,'document_delay':0,'release':False}
    handler=type('Handler',(DataPreview,),{'state':state})
    server=PreviewServer(('127.0.0.1',0),functools.partial(handler,directory=str(dist),bootstrap=True))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}';core=core_files(dist)
    context=await browser.new_context(viewport={'width':390,'height':844},service_workers='block')
    await context.add_init_script("if(location.protocol==='http:'){localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+3600))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}}}")
    results={'label':label};denied=[];mode={'block':False,'css':False}
    async def assets(route):
        path=urlparse(route.request.url).path
        if (mode['css'] and path.endswith('.css')) or (mode['block'] and path.endswith('.js') and path not in core):
            denied.append(path);await route.fulfill(status=503,body='Synthetic unavailable file',content_type='text/css' if path.endswith('.css') else 'application/javascript');return
        await route.continue_()
    await context.route('**/assets/**',assets)
    cases=[('settings','/settings','select[aria-label="Summary provider"]'),
           ('podcast','/viewer/699acfb5de29766da924dee1','text=Readable podcast overview.'),
           ('video','/videos/bc2c988b-2b4','article'),('local','/videos/local-completed','article')]
    try:
        for name,path,selector in cases:
            page=await context.new_page();browser_errors=[]
            page.on('pageerror',lambda error:browser_errors.append(str(error)[:400]))
            page.on('console',lambda message:browser_errors.append(message.text[:400]) if message.type=='error' else None)
            mode.update(block=False,css=False)
            await page.goto(origin+'/podcasts',wait_until='domcontentloaded')
            await page.wait_for_function("!document.querySelector('#startup-shell') && !!document.querySelector('main h1')")
            mode['block']=True;start=time.monotonic()
            await page.evaluate("path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))}",path)
            opened=False
            try:
                await page.locator(selector).first.wait_for(timeout=3500);opened=True
                if name=='settings':await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]').disabled",timeout=1000)
            except BrowserTimeout:pass
            results[name]={'opens_without_optional_files':opened,'milliseconds':round((time.monotonic()-start)*1000)}
            if label.startswith('after'):assert opened,results
            if opened and name in {'video','local'} and label.startswith('after'):
                await page.wait_for_function("Array.from(document.querySelectorAll('article img')).some(image=>image.complete && image.naturalWidth>0)",timeout=3000)
                results[name]['screenshots_without_formatter']=True
            if opened and name=='local' and label.startswith('after'):
                await page.get_by_role('button',name='Reload formatting',exact=True).wait_for(timeout=3000)
                mode['block']=False
                await page.get_by_role('button',name='Reload formatting',exact=True).click()
                try:
                    await page.locator('article[data-rendering="formatted"]').wait_for(timeout=6000)
                except BrowserTimeout:
                    print(json.dumps({'label':label,'recovery_failure':{'path':urlparse(page.url).path,'boot_parameter':'__xyz_boot' in page.url,'fallback':await page.locator('article[data-rendering="plain"]').count(),'reload_button':await page.get_by_role('button',name='Reload formatting',exact=True).count(),'startup':await page.locator('#startup-shell').count(),'errors':browser_errors[-8:]}}),flush=True)
                    raise
                assert '__xyz_boot' not in page.url
                assert await page.locator('script[type="importmap"]').count()==1
                results['formatting_recovers']=True
            await page.close()
        mode.update(block=False,css=True);page=await context.new_page()
        await page.goto(origin+'/settings',wait_until='domcontentloaded')
        try:await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=3500);results['opens_with_stylesheet_requests_denied']=True
        except BrowserTimeout:results['opens_with_stylesheet_requests_denied']=False
        if label.startswith('after'):assert results['opens_with_stylesheet_requests_denied'],results
        results['denied_requests']=len(denied)
        print(json.dumps(results),flush=True)
    finally:
        await context.close();server.shutdown()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);parser.add_argument('--webkit',action='store_true');args=parser.parse_args()
    async with async_playwright() as p:
        for label,dist in [('before',args.baseline_dist),('after',Path(__file__).resolve().parents[1]/'web/dist')]:
            if not dist:continue
            browser=await p.chromium.launch(executable_path=args.browser_path,headless=True,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
            await check(browser,dist,label);await browser.close()
        if args.webkit:
            browser=await p.webkit.launch(headless=True);await check(browser,Path(__file__).resolve().parents[1]/'web/dist','after-webkit');await browser.close()
if __name__=='__main__':asyncio.run(main())
