"""Synthetic visual and failure-recovery checks; no production content."""
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve, fixtures
from scripts.check_page_loading import token
from playwright.async_api import async_playwright

async def main():
    server=serve(Path('web/dist').resolve()); origin=f'http://127.0.0.1:{server.server_port}'
    _, summary=fixtures()
    async with async_playwright() as p:
        launch={}
        if Path('/tmp/chromium').exists():
            launch={'executable_path':'/tmp/chromium','args':json.loads(Path('/tmp/xyz-chromium-args.json').read_text())}
        browser=await p.chromium.launch(**launch)
        try:
            for width in (390,1440):
                if not browser.is_connected(): browser=await p.chromium.launch(**launch)
                context=await browser.new_context(viewport={'width':width,'height':960},service_workers='block')
                await context.add_init_script('''if(location.protocol==='http:'){localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;send(){}close(){}};}'''.replace('TOKEN',json.dumps(token(int(time.time())+3600))))
                page=await context.new_page(); errors=[]; summary_reads=0
                page.on('pageerror',lambda e:errors.append(str(e)))
                async def api(route):
                    nonlocal summary_reads
                    path=urlparse(route.request.url).path;body={}
                    if path=='/api/auth/config':body={'supabase_enabled':True}
                    elif path=='/api/auth/me':body={'id':'bench','email':'','authenticated':True}
                    elif path=='/api/library':body={'items':[{'id':str(i),'title':f'Saved lesson {i}','kind':'podcast' if i%2 else 'video','status':'completed','date':'2026-10-21','source':'Learning studio','thumbnail':'https://image.xyzcdn.net/fixture.jpg','topics_count':8,'duration':1200} for i in range(8)]+[{'id':'failed','title':'Failed task should be hidden','kind':'video','status':'failed'}],'next_cursor':None}
                    elif path=='/api/image-proxy':
                        return await route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#224c65"/><circle cx="320" cy="150" r="65" fill="#66c2c2"/><text x="220" y="285" fill="white" font-size="30">Learning studio</text></svg>')
                    elif path=='/api/stats':body={key:12 for key in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_channels','total_videos','completed_videos']}
                    elif path=='/api/summaries/recent':body=[]
                    elif path=='/api/video-notes/recent':body={'tasks':[]}
                    elif path=='/api/summaries/bench':
                        summary_reads+=1
                        if summary_reads==1:return await route.abort('failed')
                        body=summary
                    elif path=='/api/new-episodes':body={'episodes':[]}
                    elif path=='/api/jobs':body={'jobs':[]}
                    elif path=='/api/video-notes/tasks':body={'tasks':[]}
                    await route.fulfill(content_type='application/json',body=json.dumps(body))
                await page.route('**/api/**',api)
                await page.goto(origin+'/library',wait_until='domcontentloaded');await page.get_by_role('heading',name='Saved lesson 0',exact=True).wait_for()
                assert not await page.get_by_text('Failed task should be hidden',exact=True).count()
                await page.wait_for_function("document.querySelector('.library-artwork img')?.naturalWidth>0")
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.screenshot(path=f'/tmp/library-visual-{width}.png')
                await page.get_by_role('button',name='list layout',exact=True).click()
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                await page.goto(origin+'/',wait_until='domcontentloaded');await page.locator('.dashboard-stats svg').first.wait_for()
                colors=await page.locator('.dashboard-stats svg').evaluate_all('(nodes)=>nodes.map(n=>getComputedStyle(n).color)')
                assert len(set(colors))>=5,colors
                await page.goto(origin+'/viewer/bench',wait_until='domcontentloaded');await page.get_by_role('heading',name='Overview',exact=True).wait_for()
                assert summary_reads==2,summary_reads
                assert not errors,errors
                print(json.dumps({'viewport':width,'artwork_loaded':True,'failed_tasks_hidden':True,'distinct_stat_colors':len(set(colors)),'network_failure_recovered':True,'errors':len(errors)}))
                if launch: await browser.close()
                else: await context.close()
        finally:await browser.close();server.shutdown()

if __name__=='__main__':asyncio.run(main())
