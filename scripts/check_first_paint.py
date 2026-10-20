"""Prove navigation remains visible while framework assets take six seconds.

Synthetic session and data only. No production credentials or notes.
"""
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


async def check(browser, dist, label, output):
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Preview,directory=str(dist),bootstrap=True))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    context=await browser.new_context(viewport={'width':390,'height':844})
    await context.add_init_script('''if(location.protocol==='http:'){
      localStorage.setItem('xyz_remember_me','true');
      localStorage.setItem('xyz_access_token',TOKEN);
      localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
      window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),5)}send(v){if(JSON.parse(v).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),5)}close(){this.readyState=3}};
    }'''.replace('TOKEN',json.dumps(token(int(time.time())+3600))))
    page=await context.new_page();errors=[];reads=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    start=time.monotonic()
    async def api(route):
        path=urlparse(route.request.url).path
        reads.append((path,round((time.monotonic()-start)*1000)))
        body={};delay=2
        if path=='/api/auth/config':body={'supabase_enabled':True,'supabase_url':'https://example.supabase.co'}
        elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True};delay=3
        elif path=='/api/settings':body={'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq','llm_model':'openai/gpt-oss-120b','groq_available':True,'check_interval':3600}
        elif path=='/api/jobs':body={'jobs':[]}
        elif path=='/api/video-notes/tasks':body={'tasks':[]}
        await asyncio.sleep(delay)
        try:await route.fulfill(body=json.dumps(body),content_type='application/json')
        except Exception:pass
    failures={'mode':'','count':0}
    entry=re.search(r'<script type="module"[^>]*src="([^"]+)"', (dist/'index.html').read_text()).group(1)
    async def assets(route):
        if failures['mode']:
            if urlparse(route.request.url).path==entry and failures['mode'] in ('once','always'):
                failures['count']+=1
                if failures['mode']=='once':failures['mode']='fast'
                return await route.fulfill(status=404,body='Replaced app entry',content_type='text/plain')
            await route.continue_();return
        await asyncio.sleep(6)
        await route.continue_()
    await page.route('**/api/**',api);await page.route('**/assets/**',assets)
    try:
        await page.goto(f'http://127.0.0.1:{server.server_port}/settings',wait_until='commit')
        await page.locator('header').first.wait_for(timeout=25000)
        navigation_ms=round((time.monotonic()-start)*1000)
        await page.screenshot(path=str(output/f'{label}-first-frame.png'))
        await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=25000)
        await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]').disabled")
        ready_ms=round((time.monotonic()-start)*1000)
        report={'label':label,'navigation_ms':navigation_ms,'settings_ready_ms':ready_ms,'settings_request_ms':[t for p,t in reads if p=='/api/settings'],'errors':errors[:]}
        print(json.dumps(report),flush=True)
        if label=='after':
            assert navigation_ms<1500,report
            assert len(report['settings_request_ms'])==1,report
            assert report['settings_request_ms'][0]<1500,report
            assert not errors,report
            failures.update(mode='once',count=0)
            origin=f'http://127.0.0.1:{server.server_port}'
            await page.goto(origin+'/settings?probe=keep#section',wait_until='commit')
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=15000)
            assert failures['count']==1,failures
            assert 'probe=keep' in page.url and '__xyz_boot' not in page.url and page.url.endswith('#section'),page.url
            report['stale_entry_recovered']=True
            await page.evaluate("sessionStorage.removeItem('xyz:entry-recovery')")
            failures.update(mode='always',count=0)
            await page.goto(origin+'/settings',wait_until='commit')
            await page.locator('#startup-retry').wait_for(state='visible',timeout=10000)
            await page.wait_for_timeout(300)
            assert failures['count']==2,failures
            assert await page.get_by_role('link',name='Library',exact=True).is_visible()
            report['entry_outage_bounded']=True
            print(json.dumps(report),flush=True)
        return report
    finally:
        await context.close();server.shutdown()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);parser.add_argument('--output',type=Path,default=Path('/tmp/xyz-first-paint'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    reports=[]
    async with async_playwright() as p:
        for label,dist in [('before',args.baseline_dist),('after',Path(__file__).resolve().parents[1]/'web/dist')]:
            if not dist:continue
            browser=await p.chromium.launch(executable_path=args.browser_path,headless=True,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
            reports.append(await check(browser,dist,label,args.output));await browser.close()
    (args.output/'results.json').write_text(json.dumps(reports,indent=2))
if __name__=='__main__':asyncio.run(main())
