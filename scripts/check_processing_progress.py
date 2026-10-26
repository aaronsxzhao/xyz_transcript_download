"""Exercise the shipped client with silent video sockets and fast completions.

All content/accounts are synthetic. No external model or mutation is issued.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


async def check(browser,origin,width):
    state={'case':'slow','phase':'discovered','accepted':False,'progress_reads':0,'detail_reads':0,'version':1}
    base=datetime.now(timezone.utc).timestamp()-60
    def task():
        ident='slow' if state['case']=='slow' else 'fast'
        status=state['phase']
        return {'id':ident,'url':'https://writer.substack.com/p/'+ident,'platform':'substack','channel':'Writer','title':'Synthetic '+ident+' import',
                'status':status,'progress':{'discovered':0,'pending':0,'summarizing':74,'success':100}[status],
                'message':status,'style':'original','model':'','formats':['original'],'duration':0,'thumbnail':'',
                'markdown':'# Synthetic import\n\nFull source text.','transcript':None,'error':'',
                'created_at':datetime.fromtimestamp(base,timezone.utc).isoformat(),
                'updated_at':datetime.fromtimestamp(base+state['version'],timezone.utc).isoformat()}
    context=await browser.new_context(viewport={'width':width,'height':900},service_workers='block')
    await context.add_init_script('''
      localStorage.setItem('xyz_remember_me','true');
      localStorage.setItem('xyz_access_token',TOKEN);
      localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
      const realNow=Date.now;Date.now=()=>realNow()+300000;
      window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}
        send(v){if(JSON.parse(v).type==='auth'){
          setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),1);
          let revision=1;this.timer=setInterval(()=>this.onmessage?.({data:JSON.stringify({type:'job_update',job:{job_id:'other',episode_title:'Parallel podcast',status:'transcribing',progress:40,created_at:Date.now()/1000,revision:++revision}})}),500)
        }}close(){clearInterval(this.timer);this.readyState=3}}
    '''.replace('TOKEN',json.dumps(token(int(time.time())+7200))))
    async def api(route):
        path=urlparse(route.request.url).path
        body={}
        if path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
        elif path=='/api/auth/config':body={'supabase_enabled':True}
        elif path=='/api/settings':body={'llm_provider':'groq','llm_model':'openai/gpt-oss-120b','groq_available':True,'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_key_saved':True,'whisper_key_saved':True}
        elif path=='/api/cookies':body={'cookies':[]}
        elif path=='/api/jobs':body={'jobs':[]}
        elif path=='/api/performance':return await route.fulfill(status=204)
        elif path=='/api/video-notes/channels':body={'channels':[{'channel':'Writer','platform':'substack','total':1,'done':0}]}
        elif path=='/api/video-notes/tasks/by-channel':body={'tasks':[task()] if state['case']=='slow' or state['accepted'] else [],'next_cursor':None}
        elif path=='/api/video-notes/progress':
            state['progress_reads']+=1
            body={'tasks':[task()] if state['phase']!='discovered' else []}
        elif path=='/api/video-notes/tasks/slow/retry':
            state.update(phase='pending',accepted=True,version=2);body={'task_id':'slow'}
        elif path=='/api/video-notes/generate-json':
            state.update(phase='success',accepted=True,version=4);body={'task_id':'fast'}
        elif path=='/api/video-notes/tasks/fast':
            state['detail_reads']+=1
            return await route.fulfill(status=503,json={'detail':'Synthetic detail read unavailable'})
        elif path=='/api/content-updates':body={'items':[]}
        elif path.startswith('/api/video-notes/tasks/'):body=task()
        return await route.fulfill(json=body)
    await context.route('**/api/**',api)
    page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    await page.goto(origin+'/videos?platform=substack&channel=Writer',wait_until='domcontentloaded')
    row=page.locator('.video-task-list')
    await row.get_by_role('button',name='Process',exact=True).click()
    await row.get_by_text('Queued',exact=True).wait_for(timeout=5000)
    state.update(phase='summarizing',version=3)
    try: await row.get_by_text('Generating summary',exact=True).wait_for(timeout=10000)
    except Exception:
        print(json.dumps({'state':state,'body':await page.locator('body').inner_text(),'errors':errors}),flush=True)
        raise
    state.update(phase='success',version=4)
    await row.get_by_role('link',name='View',exact=True).wait_for(timeout=10000)
    assert state['progress_reads']>=2
    state.update(case='fast',phase='discovered',accepted=False,version=1)
    await page.goto(origin+'/videos?platform=substack&channel=Writer&import=https%3A%2F%2Fwriter.substack.com%2Fp%2Ffast',wait_until='domcontentloaded')
    await page.get_by_role('button',name='Import content',exact=True).click()
    await page.locator('.video-task-list').get_by_role('heading',name='Synthetic fast import',exact=True).wait_for(timeout=10000)
    await page.locator('.video-task-list').get_by_role('link',name='View',exact=True).wait_for(timeout=10000)
    assert state['detail_reads']>=1
    assert not await page.locator('.video-task-list').get_by_text('Queued',exact=True).count()
    assert not errors,errors
    print(json.dumps({'width':width,'parallel_stream_progress':True,'completion_visible':True,'fast_completion_with_unavailable_detail':True,'client_clock_skew_minutes':5,'errors':errors}),flush=True)
    await context.close()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--widths',type=int,nargs='+',default=[390,1440]);args=parser.parse_args()
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            for width in args.widths:await check(browser,f'http://127.0.0.1:{server.server_port}',width)
            await browser.close()
    finally:server.shutdown()


if __name__=='__main__':asyncio.run(main())
