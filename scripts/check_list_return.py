"""List -> summary -> list position checks using only controlled local APIs."""
import argparse, asyncio, json, sys, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures, serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright

async def check(browser,origin,width,design,theme,output,kinds):
    task,summary=fixtures()
    base={k:v for k,v in task.items() if k not in ('markdown','transcript','versions')}
    tasks=[{**base,'id':f'v{i}','title':f'Controlled video {i:02}', 'channel':'Controlled channel','platform':'youtube','thumbnail':'','created_at':f'2026-11-14T00:00:{59-i:02}Z'} for i in range(55)]
    episodes=[{'eid':f'e{i}','pid':'show','title':f'Controlled episode {i:02}','duration':1800,'pub_date':'2026-11-14','has_summary':True,'has_transcript':True,'key_points_count':2} for i in range(55)]
    podcast={'pid':'show','title':'Controlled podcast','platform':'apple','episode_count':55,'summarized_count':55,'cover_url':'','description':'Controlled list'}
    context=await browser.new_context(viewport={'width':width,'height':900},service_workers='block')
    await context.add_init_script('''localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));localStorage.setItem('xyz:design',DESIGN);localStorage.setItem('xyz:color-theme',THEME);window.WebSocket=class{static OPEN=1;readyState=1;send(){}close(){}}'''.replace('TOKEN',json.dumps(token(int(time.time())+7200))).replace('DESIGN',json.dumps(design)).replace('THEME',json.dumps(theme)))
    errors=[];writes=[]
    async def api(route):
        u=urlparse(route.request.url);q=parse_qs(u.query);p=u.path;body={}
        if route.request.method not in ('GET','HEAD'):
            if p!='/api/performance':writes.append(p)
            return await route.fulfill(status=204)
        if p=='/api/auth/config':body={'supabase_enabled':True}
        elif p=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
        elif p=='/api/jobs':body={'jobs':[]}
        elif p=='/api/video-notes/progress':body={'tasks':[]}
        elif p=='/api/content-updates':body={'items':[]}
        elif p=='/api/video-notes/channels':body={'channels':[{'channel':'Controlled channel','platform':'youtube','total':55,'done':55}]}
        elif p=='/api/video-notes/tasks/by-channel':
            rows=tasks if q.get('sort')!=['oldest'] else list(reversed(tasks));start=40 if q.get('cursor') else 0
            body={'tasks':rows[start:start+40],'next_cursor':'more' if start==0 else None};await asyncio.sleep(.3)
        elif p=='/api/podcasts':body=[podcast]
        elif p=='/api/podcasts/show':body=podcast
        elif p=='/api/podcasts/content':
            start=int(q.get('offset',['0'])[0]);body=episodes[start:start+50];await asyncio.sleep(.3)
        elif p.startswith('/api/summaries/'):
            eid=p.rsplit('/',1)[-1];body={**summary,'episode_id':eid,'title':'Controlled episode '+eid[1:].zfill(2),'overview':'\n\n'.join('Controlled long reading paragraph. '*35 for _ in range(35))}
        elif p.startswith('/api/video-notes/tasks/'):
            eid=p.rsplit('/',1)[-1];body={**task,'id':eid,'title':'Controlled video '+eid[1:].zfill(2),'markdown':'# Controlled note\n\n'+'\n\n'.join('Long reading paragraph. '*40 for _ in range(40)),'transcript':None,'versions':[]}
        return await route.fulfill(json=body)
    await context.route('**/api/**',api);page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    cases=[]
    for kind,url in [('video','/videos?platform=youtube&channel=Controlled+channel'),('podcast','/podcasts/show/episodes')]:
        if kind not in kinds:continue
        await page.goto(origin+url,wait_until='domcontentloaded')
        await page.get_by_role('heading',name='Controlled '+('video' if kind=='video' else 'episode')+' 00',exact=True).wait_for()
        if kind=='video':
            await page.get_by_role('textbox',name='Search videos',exact=True).fill('Controlled')
            await page.get_by_role('combobox',name='Channel video status',exact=True).select_option('success')
            await page.get_by_role('combobox',name='Channel video order',exact=True).select_option('oldest')
            await page.wait_for_timeout(900)
            await page.get_by_role('button',name='Show more videos',exact=True).click()
            eid='v2';href='/videos/'+eid
        else:
            await page.get_by_role('button',name='Load more episodes',exact=True).click()
            eid='e52';href='/viewer/'+eid
        link=page.locator(f'a[href="{href}"]')
        for label,mode in [('link','link'),('card-browser-back','card'),('reader-reload','reload')]:
            await link.wait_for();await link.scroll_into_view_if_needed()
            await link.evaluate('(el)=>{const m=document.querySelector("main");m.scrollTop+=el.getBoundingClientRect().top-250}')
            await page.wait_for_timeout(150);before=await link.evaluate('(el)=>({top:el.getBoundingClientRect().top,scroll:document.querySelector("main").scrollTop})')
            if output:await page.screenshot(path=str(output/f'{kind}-{design}-{theme}-{width}-{label}-entry.png'))
            if mode=='card':await page.get_by_role('heading',name='Controlled '+('video' if kind=='video' else 'episode')+(' 02' if kind=='video' else ' 52'),exact=True).click()
            else:await link.click()
            await page.locator('.reader-body').first.wait_for();await page.wait_for_function('document.querySelector("main").scrollHeight>4000');await page.locator('main').evaluate('(el)=>el.scrollTop=2400');await page.wait_for_timeout(850)
            assert await page.locator('main').evaluate('(el)=>el.scrollTop')>=2000
            if mode=='card':
                # Reading longer than the cache freshness window must retain loaded pages.
                await page.evaluate('()=>{const now=Date.now;Date.now=()=>now()+120000}')
            if mode=='reload':
                await page.reload(wait_until='domcontentloaded');await page.locator('.reader-body').first.wait_for();await page.wait_for_function('document.querySelector("main").scrollTop>=2000')
            if mode=='card':await page.go_back(wait_until='domcontentloaded')
            else:await page.get_by_role('button',name='Go back',exact=True).click()
            await page.wait_for_timeout(1000)
            if output:await page.screenshot(path=str(output/f'{kind}-{design}-{theme}-{width}-{label}-return-observed.png'))
            await link.wait_for(timeout=5000)
            after=await link.evaluate('(el)=>({top:el.getBoundingClientRect().top,scroll:document.querySelector("main").scrollTop})')
            if output:await page.screenshot(path=str(output/f'{kind}-{design}-{theme}-{width}-{label}-return.png'))
            if abs(after['top']-before['top'])>1:print(json.dumps({'failure_storage':await page.evaluate('Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.includes("reading") || k.includes("controls")))')}),flush=True)
            assert abs(after['top']-before['top'])<=1,(kind,label,before,after)
            if kind=='video':
                assert await page.get_by_role('textbox',name='Search videos',exact=True).input_value()=='Controlled'
                assert await page.get_by_role('combobox',name='Channel video status',exact=True).input_value()=='success'
                assert await page.get_by_role('combobox',name='Channel video order',exact=True).input_value()=='oldest'
                assert await page.locator('.video-task-list a[href^="/videos/"]').count()==55
            else:assert await page.locator('[data-episode-id]').count()==55
            cases.append({'kind':kind,'case':label,'before':before,'after':after})
        previous=await page.locator('main').evaluate('(el)=>el.scrollTop');await page.locator('main').hover();await page.mouse.wheel(0,-400);await page.wait_for_timeout(400)
        moved=await page.locator('main').evaluate('(el)=>el.scrollTop');assert moved<previous-100
        await page.wait_for_timeout(400);assert abs(await page.locator('main').evaluate('(el)=>el.scrollTop')-moved)<=1
    assert not writes and not errors,(writes,errors)
    await context.close();r={'width':width,'design':design,'theme':theme,'cases':cases};print(json.dumps(r),flush=True);return r

async def main():
    p=argparse.ArgumentParser();p.add_argument('--kinds',nargs='+',default=['video','podcast']);p.add_argument('--designs',nargs='+',default=['classic','editorial']);p.add_argument('--themes',nargs='+',default=['light','dark']);p.add_argument('--dist',default='web/dist');p.add_argument('--webkit',action='store_true');p.add_argument('--browser-path');p.add_argument('--widths',type=int,nargs='+',default=[390,820,1440]);p.add_argument('--output',type=Path);a=p.parse_args();results=[]
    if a.output:a.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(a.dist).resolve())
    try:
        async with async_playwright() as pw:
            browser=await pw.webkit.launch() if a.webkit else await pw.chromium.launch(executable_path=a.browser_path,chromium_sandbox=True)
            try:
                for width in a.widths:
                    for design in a.designs:
                        for theme in a.themes:results.append(await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,a.output,a.kinds))
            finally:await browser.close()
    finally:
        server.shutdown()
        if a.output:(a.output/'results.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
