"""Synthetic large-channel, cache hydration, search and account-failure checks."""
import argparse,asyncio,json,time,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);args=parser.parse_args()
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.browser_path,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':960},service_workers='block')
        await context.add_init_script("if(location.protocol==='http:'){localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+3600))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}};}")
        page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        channel_requests=[];fail_accounts=True;delay_channel=0
        rows=[dict(id=f'v{i}',title=f'Lesson {i:04}',platform='youtube',channel='Large channel',status='success',created_at=f'2026-01-{i%28+1:02}T00:00:00Z',url='fixture://video',progress=100,duration=60) for i in range(2000)]
        async def api(route):
            nonlocal fail_accounts
            path=urlparse(route.request.url).path;params=parse_qs(urlparse(route.request.url).query);body={}
            if path=='/api/auth/config':body={'supabase_enabled':True}
            elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
            elif path=='/api/video-notes/tasks/by-channel':
                channel_requests.append(params);matched=[r for r in rows if params.get('q',[''])[0].lower() in r['title'].lower()]
                if params.get('status'):matched=[r for r in matched if r['status']==params['status'][0]]
                matched=sorted(matched,key=lambda r:(r['created_at'],r['id']),reverse=params.get('sort',['newest'])[0]!='oldest')
                offset=int(params.get('cursor',['0'])[0]);body={'tasks':matched[offset:offset+40],'next_cursor':str(offset+40) if len(matched)>offset+40 else None};await asyncio.sleep(delay_channel)
            elif path=='/api/video-notes/channels':body={'channels':[]}
            elif path=='/api/video-notes/progress':body={'tasks':[]}
            elif path=='/api/settings':body={'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq','llm_model':'openai/gpt-oss-120b','check_interval':3600}
            elif path=='/api/cookies':
                if fail_accounts:await route.fulfill(status=503,body='{"detail":"Temporary failure"}',content_type='application/json');return
                body={'cookies':[{'platform':'bilibili','has_cookie':True,'updated_at':'2026-10-21'}]}
            elif path=='/api/cookies/bilibili/validate':body={'valid':False,'reason':'expired','message':'Expired'}
            await route.fulfill(body=json.dumps(body),content_type='application/json')
        await page.route('**/api/**',api)
        origin=f'http://127.0.0.1:{server.server_port}'
        try:
            await page.goto(origin+'/videos?platform=youtube&channel=Large+channel')
            await page.get_by_role('button',name='Show more videos',exact=True).wait_for()
            assert await page.get_by_text('40 videos loaded',exact=True).count()==1
            await page.get_by_role('button',name='Show more videos',exact=True).click()
            await page.get_by_text('80 videos loaded',exact=True).wait_for()
            assert len(channel_requests)==2,channel_requests
            delay_channel=1
            search=page.get_by_placeholder('Search videos...')
            await search.fill('Lesson 1999')
            assert await page.get_by_text('80 videos',exact=True).count()>=1
            await page.get_by_text('1 videos loaded',exact=True).wait_for()
            assert channel_requests[-1]['q']==['Lesson 1999']
            assert not await page.get_by_role('button',name='Show more videos',exact=True).count()
            assert not await page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('xyz_cache_')&&k.includes('channel_videos'))")
            disk=await page.evaluate("""()=>new Promise(resolve=>{const req=indexedDB.open('xyz-private-cache');req.onsuccess=()=>{const r=req.result.transaction('entries').objectStore('entries').getAll();r.onsuccess=()=>resolve(r.result.map(e=>e.key))}})""")
            assert any('channel_videos' in k for k in disk),disk
            await page.goto(origin+'/settings')
            await page.get_by_role('button',name='Platform Accounts',exact=True).click()
            await page.get_by_role('button',name='Retry accounts',exact=True).wait_for()
            assert not await page.get_by_text('Not connected',exact=True).count()
            fail_accounts=False
            await page.get_by_role('button',name='Retry accounts',exact=True).click()
            await page.get_by_role('button',name='Check connection',exact=True).wait_for()
            await page.get_by_role('button',name='Check connection',exact=True).click()
            await page.get_by_text('Connection expired. Sign in again below.',exact=True).wait_for()
            assert not errors,errors
            print(json.dumps({'channel_first_page':40,'channel_next_page':80,'search_server_filtered':True,'indexeddb_persisted':True,'accounts_failure_retry_expiry':True,'errors':errors}))
        finally:await context.close();await browser.close();server.shutdown()

if __name__=='__main__':asyncio.run(main())
