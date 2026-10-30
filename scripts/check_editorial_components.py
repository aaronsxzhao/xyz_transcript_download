"""Inspect real appearance controls and long Library titles with synthetic APIs."""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures

CONTROL = r'''e => {
 const rgb=s=>{if(s.startsWith('rgb'))return (s.match(/[\d.]+/g)||[]).map(Number);const c=document.createElement('canvas');c.width=c.height=1;const x=c.getContext('2d');x.fillStyle=s;x.fillRect(0,0,1,1);const v=[...x.getImageData(0,0,1,1).data];return [v[0],v[1],v[2],v[3]/255]};
 const lum=c=>{const v=c.slice(0,3).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};
 function contrast(el,pseudo){const css=getComputedStyle(el,pseudo);let bg=[255,255,255];const parents=[];for(let p=el;p;p=p.parentElement)parents.unshift(p);
  for(const p of parents){const c=rgb(getComputedStyle(p).backgroundColor),a=c[3]??1;if(c.length)bg=bg.map((v,i)=>c[i]*a+v*(1-a))}
  if(pseudo){const c=rgb(css.backgroundColor),a=c[3]??1;bg=bg.map((v,i)=>c[i]*a+v*(1-a))}
  const a=lum(rgb(css.color)),b=lum(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
 }
 const text=[...e.querySelectorAll('span')].filter(s=>s.innerText.trim()&&s.getClientRects().length);
 return {name:e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||e.type,classes:e.className,
  fg:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor,radius:getComputedStyle(e).borderRadius,
  disabled:!!e.disabled,native:['checkbox','radio','range'].includes(e.type),ratio:Math.min(contrast(e),...text.map(s=>contrast(s))),
  fileRatio:e.type==='file'?contrast(e,'::file-selector-button'):null,
  text:!!e.innerText?.trim(),tag:e.tagName,shadow:getComputedStyle(e).boxShadow,outline:getComputedStyle(e).outlineStyle};
}'''

async def run(browser, origin, theme, widths, output, routes, design="editorial"):
    context=await context_for(browser, widths[0])
    jobs=[{'job_id':'fixture-job','episode_title':'A failed task to review','status':'failed','created_at':1700000000,'progress':0,'message':'Connection needs attention'}]
    await context.route('**/api/jobs',lambda r:r.fulfill(json={'jobs':jobs}))
    await context.add_init_script("window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:"+json.dumps(jobs)+",video_tasks:[]})}),1)}close(){}}")
    async def library(route):
        titles=['【深度访谈】'+ '长中文标题需要完整换行，不能遮挡来源和操作。'*8,
                'AnUnbrokenEnglishTitleWithoutAnySpaces'*8,
                'A long English title that needs sensible wrapping and space for its source '*5]
        await route.fulfill(json={'items':[{'id':str(i),'kind':'video','content_type':'video','title':t,'source':'A very long source name '*8,'platform':'youtube','status':'completed','date':'2026-10-29'} for i,t in enumerate(titles)],'next_cursor':None})
    await context.route('**/api/library?*',library)
    await context.route('**/api/cookies/douyin/diagnose',lambda r:r.fulfill(json={'has_cookie':False,'looks_usable':False,'message':'No saved cookies','present':[],'missing':[],'cookie_count':0,'domains':[]}))
    task, _ = fixtures()
    task.update(versions=[], channel='Synthetic channel', markdown='# Synthetic note\n\n![Chart caption](/fixture.svg)\n\n## Second section\n\nReadable text.')
    await context.route('**/api/video-notes/tasks/bench',lambda r:r.fulfill(json=task))
    await context.route('**/api/video-notes/tasks/bench?*',lambda r:r.fulfill(json=task))
    await context.route('**/api/video-notes/tasks/by-channel*',lambda r:r.fulfill(json={'tasks':[task],'next_cursor':None}))
    await context.route('**/fixture.svg',lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="400" height="240" fill="#ddd"/><text x="30" y="100" font-size="24">Synthetic chart</text></svg>'))
    await context.route('**/api/bilibili-favorites',lambda r:r.fulfill(json={'folders':[{'id':1,'title':'Saved videos','count':1}]}))
    await context.route('**/api/bilibili-favorites/1?*',lambda r:r.fulfill(json={'videos':[{'bvid':'BVfixture','title':'A saved video to review','url':'https://example.test/video','thumbnail':'','duration':300,'uploader':'Fixture','available':True,'imported':False}],'page':1,'has_more':False}))
    page=await context.new_page();errors=[];records=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    async def capture(step, states=True, scope="body"):
        filename=re.sub(r'[^A-Za-z0-9_.-]', '-', step)
        await page.wait_for_timeout(200)
        assert not await page.get_by_text('This page could not open',exact=True).count(), (step,'page failed')
        controls=page.locator(scope).locator('button,summary,select,input:not([type=hidden]),textarea,a[href]')
        for control in await controls.all():
            if not await control.is_visible(): continue
            variants=['default','hover','focus'] if states and not await control.is_disabled() else ['default']
            if len(variants)>1 and scope=='body' and await control.evaluate("e=>e.tagName==='BUTTON'&&!e.hasAttribute('aria-expanded')&&!e.classList.contains('reader-screenshot')"):
                variants.append('active')
            for state in variants:
                if state=='hover':
                    await control.hover(force=True);await page.wait_for_timeout(170)
                elif state=='focus':
                    await control.focus()
                elif state=='active':
                    await control.hover(force=True);await page.mouse.down()
                info=await control.evaluate(CONTROL);info.update(design=design,theme=theme,step=step,state=state);records.append(info)
                if design=='editorial' and state=='focus' and info['tag'] in ['INPUT','SELECT','TEXTAREA']:
                    assert info['shadow']=='none', (step,'legacy focus ring',info)
                if state=='active':
                    await page.mouse.move(0,0);await page.mouse.up()
                if not info['disabled'] and not info['native']:
                    threshold=4.5 if info['text'] else 3
                    assert info['ratio']>=threshold, (step,state,info)
                    if info['fileRatio'] is not None: assert info['fileRatio']>=4.5,(step,info)
        await page.mouse.move(0,0)
        await page.screenshot(path=str(output/f'{theme}-{filename}.png'),full_page=True)
        if scope == 'body' and await page.locator('main').count():
            await page.locator('main').first.evaluate('e=>e.scrollTo(0,0)')
            await page.screenshot(path=str(output/f'{theme}-{filename}-top.png'),full_page=True)
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),(step,'page overflow')
        for heading in await page.locator('.publication-feature h2').all():
            assert await heading.evaluate('e=>e.getBoundingClientRect().height<=parseFloat(getComputedStyle(e).lineHeight)*4+1'),(step,'featured title pushes content away')
        assert not errors,(step,errors)
        print(json.dumps({'theme':theme,'step':step,'controls_checked':len(records)}),flush=True)
    try:
        for route in routes:
            await page.goto(origin+route);await page.locator('h1').first.wait_for();await choose(page,design,theme)
            await capture(route.strip('/').replace('/','-') or 'dashboard')
            if route=='/library':
                await page.get_by_role('button',name='Open processing tasks',exact=True).click();await capture('processing-drawer',scope='[role=dialog]');await page.keyboard.press('Escape')
                for width in widths:
                    await page.set_viewport_size({'width':width,'height':900})
                    for layout in ['grid','list']:
                        await page.get_by_role('button',name=layout+' layout',exact=True).click()
                        await page.wait_for_timeout(100)
                        geometry=await page.locator('.library-card').evaluate_all('''cards=>cards.map(c=>{const h=c.querySelector('h2'),p=h.nextElementSibling,t=h.getBoundingClientRect(),s=p.getBoundingClientRect(),b=c.getBoundingClientRect();return {wrap:h.scrollWidth<=h.clientWidth+1,inside:t.left>=b.left&&t.right<=b.right+1,separate:t.bottom<=s.top+1}})''')
                        assert all(all(g.values()) for g in geometry),(theme,width,layout,geometry)
                        for card in await page.locator('.library-card').all():
                            await card.hover();await page.wait_for_timeout(170)
                            heading=card.locator('h2')
                            assert (await heading.evaluate(CONTROL))['ratio']>=4.5,(design,theme,width,layout,'title hover contrast')
                        await capture(f'library-{width}-{layout}',states=False)
                await page.set_viewport_size({'width':widths[0],'height':900})
            elif route=='/podcasts':
                await page.get_by_role('button',name='Add Podcast',exact=True).click();await capture('podcast-add')
                await page.get_by_role('button',name='Upload Audio',exact=True).click();await page.get_by_label('Audio file',exact=True).wait_for();await capture('podcast-upload')
            elif route=='/videos':
                await page.get_by_role('button',name='Add content',exact=True).click();await page.get_by_label('Content URL',exact=True).wait_for();await capture('video-create')
                await page.get_by_role('button',name='Advanced Options',exact=True).click();await capture('video-advanced')
                await page.get_by_role('button',name='Close new video note form',exact=True).click()
                await page.get_by_role('button',name='Bilibili favorites',exact=True).click();await page.get_by_label('Favorite folder',exact=True).wait_for();await capture('bilibili-favorites')
                await page.get_by_label('Select available videos on this page',exact=True).check();await capture('bilibili-selected')
            elif route=='/settings':
                await page.get_by_label('Transcription provider',exact=True).select_option('custom');await page.get_by_label('Transcription Base URL',exact=True).wait_for();await capture('custom-transcription')
                await page.get_by_label('Summary provider',exact=True).select_option('custom');await capture('custom-summary')
                for section in ['Platform Accounts','Tools & Data']:
                    await page.get_by_role('button',name=section,exact=True).click();await capture(section.replace(' ','-'))
                    if section=='Platform Accounts':
                        for platform in ['YouTube','Douyin','Kuaishou']:
                            await page.get_by_role('button',name=platform,exact=True).click();await capture('account-'+platform)
            elif route in ['/videos/bench','/viewer/bench']:
                await page.get_by_role('button',name='Export',exact=True).click();await capture(route.strip('/').replace('/','-')+'-export',scope='.reader-menu-panel');await page.keyboard.press('Escape')
                await page.get_by_role('button',name='Reading appearance',exact=True).click();await page.get_by_role('group',name='Text size',exact=True).wait_for();await capture(route.strip('/').replace('/','-')+'-appearance',scope='.reader-menu-panel');await page.keyboard.press('Escape')
                await page.get_by_role('button',name='More summary actions',exact=True).click();await capture(route.strip('/').replace('/','-')+'-more',scope='.reader-menu-panel');await page.keyboard.press('Escape')
                if route=='/videos/bench':
                    await page.locator('button.reader-screenshot').first.click();await page.locator('.gallery-viewport img').wait_for(state='visible');await capture('screenshot-gallery',scope='.screenshot-gallery');await page.keyboard.press('Escape')
        if '/settings' in routes:
            await context.close()
            context=await context_for(browser,widths[0],authenticated=False)
            await context.add_init_script("localStorage.setItem('xyz:design',"+json.dumps(design)+");localStorage.setItem('xyz:color-theme',"+json.dumps(theme)+");")
            page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(origin+'/login');await page.get_by_label('Email',exact=True).wait_for();await capture('login')
            await page.get_by_role('button',name='Sign up',exact=True).click();await capture('signup')
            await page.get_by_role('button',name='Forgot password?',exact=True).click();await capture('recovery')
            await page.goto(origin+'/reset-password#type=recovery&access_token=synthetic');await page.get_by_label('New password',exact=True).wait_for();await capture('reset-password')
        (output/f'{theme}-controls.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    except Exception:
        await page.screenshot(path=str(output/f'{theme}-failure.png'),full_page=True)
        (output/f'{theme}-controls.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        raise
    finally: await context.close()

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--routes',nargs='+',default=['/','/library','/podcasts','/videos','/settings','/podcasts/show/episodes','/videos?platform=youtube&channel=Synthetic%20channel','/videos/bench','/viewer/bench']);parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--design',choices=['classic','editorial'],default='editorial');parser.add_argument('--widths',type=int,nargs='+',default=[820,390,1440]);parser.add_argument('--output',type=Path,default=Path('/tmp/editorial-component-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for theme in ['light','dark']:await run(browser,f'http://127.0.0.1:{server.server_port}',theme,args.widths,args.output,args.routes,args.design)
            finally:await browser.close()
    finally:server.shutdown();server.server_close()
if __name__=='__main__':asyncio.run(main())
