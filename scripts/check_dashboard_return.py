"""Production-build dashboard/reader return positions with controlled local APIs."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures, serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


async def check(browser, origin, width, design, theme, output):
    task, summary = fixtures()
    entries = [{'id':str(i), 'kind':'podcast' if i % 2 else 'video',
                'title':f'Controlled summary {i}', 'source':'Controlled source',
                'date':'2026-11-14', 'status':'completed', 'topics_count':2}
               for i in range(40)]
    context = await browser.new_context(viewport={'width':width,'height':900}, service_workers='block')
    await context.add_init_script('''
        localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);
        localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
        localStorage.setItem('xyz:design',DESIGN);localStorage.setItem('xyz:color-theme',THEME);
        window.WebSocket=class{static OPEN=1;readyState=1;send(){}close(){}}
    '''.replace('TOKEN',json.dumps(token(int(time.time())+7200))).replace('DESIGN',json.dumps(design)).replace('THEME',json.dumps(theme)))
    writes, errors = [], []
    async def api(route):
        parsed=urlparse(route.request.url); path=parsed.path; query=parse_qs(parsed.query); body={}
        if route.request.method not in ('GET','HEAD'):
            if path!='/api/performance':writes.append(path)
            return await route.fulfill(status=204)
        if path=='/api/auth/config':body={'supabase_enabled':True}
        elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
        elif path=='/api/stats':body={'total_summaries':40}
        elif path=='/api/jobs':body={'jobs':[]}
        elif path=='/api/content-updates':body={'items':[]}
        elif path=='/api/video-notes/progress':body={'tasks':[]}
        elif path=='/api/library':
            ids=query.get('ids',[''])[0]; kind=query.get('kind',[''])[0]
            rows=[r for r in entries if (not kind or r['kind']==kind) and (not ids or r['kind']+':'+r['id'] in ids.split(','))]
            start=int(query.get('cursor',['0'])[0]); limit=int(query.get('limit',['12'])[0])
            body={'items':rows[start:start+limit],'next_cursor':str(start+limit) if start+limit<len(rows) else None}
            # Return restoration must survive asynchronous history/feed verification.
            await asyncio.sleep(.35)
        elif path.startswith('/api/summaries/'):
            eid=path.rsplit('/',1)[-1]
            body={**summary,'episode_id':eid,'title':f'Controlled summary {eid}',
                  'overview':'\n\n'.join('Controlled long reading paragraph. '*35 for _ in range(35))}
        elif path.startswith('/api/video-notes/tasks/'):
            eid=path.rsplit('/',1)[-1]
            body={**task,'id':eid,'title':f'Controlled summary {eid}',
                  'markdown':'# Controlled note\n\n'+'\n\n'.join('Long reading paragraph. '*40 for _ in range(40)), 'transcript':None, 'versions':[]}
        return await route.fulfill(json=body)
    await context.route('**/api/**',api)
    page=await context.new_page(); page.on('pageerror',lambda e:errors.append(str(e)))
    await page.goto(origin+'/',wait_until='domcontentloaded')
    await page.wait_for_function('''()=>document.documentElement.dataset.design===DESIGN && document.documentElement.dataset.theme===THEME'''.replace('DESIGN',json.dumps(design)).replace('THEME',json.dumps(theme)))
    recent=page.get_by_role('region',name='Recently added')
    await recent.locator('[data-recent-count="12"]').wait_for()
    await page.evaluate('document.fonts.ready')
    result={'width':width,'design':design,'theme':theme,'cases':[]}

    async def round_trip(eid, label, reload=False, browser_back=False, section='Recently added'):
        region=page.get_by_role('region',name=section,exact=True)
        href=('/viewer/' if int(eid)%2 else '/videos/')+eid
        card=region.locator(f'a[href="{href}"]')
        await card.scroll_into_view_if_needed()
        # Keep the full entry target visible so the click does not autoscroll it.
        await card.evaluate('(el)=>{const main=document.querySelector("main");main.scrollTop+=el.getBoundingClientRect().top-220}')
        await page.wait_for_timeout(100)
        before=await card.evaluate('(el)=>({top:el.getBoundingClientRect().top,scroll:document.querySelector("main").scrollTop})')
        if output:await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{label}-entry.png'))
        await card.click()
        await page.get_by_role('button',name='Go back',exact=True).wait_for()
        await page.locator('.reader-body').first.wait_for()
        await page.locator('main').evaluate('(el)=>el.scrollTop=2400')
        await page.wait_for_timeout(850)
        assert await page.locator('main').evaluate('(el)=>el.scrollTop')>=2000
        if reload:
            await page.reload(wait_until='domcontentloaded')
            await page.locator('.reader-body').first.wait_for()
            await page.wait_for_function('document.querySelector("main").scrollTop>=2000')
        if browser_back:await page.go_back(wait_until='domcontentloaded')
        else:await page.get_by_role('button',name='Go back',exact=True).click()
        await page.wait_for_url(origin+'/')
        await card.wait_for()
        await page.wait_for_function('''({href,section,top})=>{
          const root=[...document.querySelectorAll('section[aria-label]')].find(e=>e.getAttribute('aria-label')===section);
          const card=root && [...root.querySelectorAll('a[href]')].find(e=>e.getAttribute('href')===href);
          return card && Math.abs(card.getBoundingClientRect().top-top)<=1;
        }''',arg={'href':href,'section':section,'top':before['top']},timeout=10000)
        await page.wait_for_timeout(600)
        after=await card.evaluate('(el)=>({top:el.getBoundingClientRect().top,scroll:document.querySelector("main").scrollTop})')
        assert abs(after['top']-before['top'])<=1,(label,before,after)
        if output:await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{label}-return.png'))
        result['cases'].append({'case':label,'before':before,'after':after,'anchor_delta':after['top']-before['top']})

    await round_trip('3','new-history')
    await round_trip('6','different-entry')
    await round_trip('3','continue-reading',section='Continue reading')
    await recent.get_by_role('button',name='Podcasts',exact=True).click()
    await recent.locator('[data-recent-count="12"]').wait_for()
    await recent.get_by_role('button',name='Load more',exact=True).click()
    await recent.locator('[data-recent-count="20"]').wait_for()
    await round_trip('35','filtered-page-two-reload',reload=True)
    assert await recent.get_by_role('button',name='Podcasts',exact=True).get_attribute('aria-pressed')=='true'
    assert await recent.locator('[data-recent-count="20"]').count()==1
    await round_trip('31','browser-back',browser_back=True)
    # A restored position is not a scroll lock.
    previous=await page.locator('main').evaluate('(el)=>el.scrollTop')
    await page.locator('main').hover();await page.mouse.wheel(0,-400);await page.wait_for_timeout(500)
    moved=await page.locator('main').evaluate('(el)=>el.scrollTop')
    assert moved<previous-100,(previous,moved)
    await page.wait_for_timeout(500)
    assert abs(await page.locator('main').evaluate('(el)=>el.scrollTop')-moved)<=1
    assert not writes and not errors,(writes,errors)
    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
    result.update(user_scroll_free=True,writes=writes,errors=errors)
    await context.close()
    print(json.dumps(result),flush=True)
    return result


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dist',default='web/dist');parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--browser-path');parser.add_argument('--widths',type=int,nargs='+',default=[390,820,1440])
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.output:args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(args.dist).resolve());results=[]
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,chromium_sandbox=True)
            try:
                for width in args.widths:
                    for design in ['classic','editorial']:
                        for theme in ['light','dark']:
                            results.append(await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,args.output))
            finally:await browser.close()
    finally:
        server.shutdown()
        if args.output:(args.output/'results.json').write_text(json.dumps(results,indent=2))

if __name__=='__main__':asyncio.run(main())
