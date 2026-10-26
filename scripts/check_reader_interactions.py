"""Exercise real reader interactions against synthetic notes and delayed APIs.

No external accounts, private notes or mutations. Saves screenshots and JSON.
"""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures, serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


async def check(browser, origin, width, output, label):
    task, summary = fixtures()
    task['markdown'] = '# Trading review / 交易复盘\n\nA practical summary with screenshots, a table, and key decisions.\n\n' + '\n\n'.join(
        f'## {i+1}. Review the trend / 趋势分析\n\n- Identify the context before entering.\n- Wait for confirmation and manage risk.\n\n![Chart at {i}:00](/data/screenshots/bench_{i}.jpg)\n\n| Signal | Action |\n| --- | --- |\n| Breakout | Review the follow-through |\n\n' for i in range(8))
    context = await browser.new_context(viewport={'width':width,'height':960}, has_touch=width<768, permissions=['clipboard-read','clipboard-write'], service_workers='block')
    await context.add_init_script('''
        if (location.protocol === 'http:' || location.protocol === 'https:') {
        localStorage.setItem('xyz_remember_me','true');
        localStorage.setItem('xyz_access_token',TOKEN);
        localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
        window.WebSocket=class {static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),10)}send(v){if(JSON.parse(v).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),5)}close(){this.readyState=3}};
        }
    '''.replace('TOKEN',json.dumps(token(int(time.time())+3600))))
    page = await context.new_page()
    session = await context.new_cdp_session(page)
    await session.send('Emulation.setCPUThrottlingRate', {'rate':4})
    errors=[]; images=[]; requests=[]; original_requests=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    fail_videos = False
    empty_podcasts = False
    account_changed = False
    async def api(route):
        path=urlparse(route.request.url).path
        requests.append(path)
        body={}; delay=.15
        if path=='/api/auth/config': body={'supabase_enabled':True}
        elif path=='/api/auth/me':body={'id':'second' if account_changed else 'bench','email':'bench@example.com','authenticated':True}
        elif path=='/api/video-notes/tasks/bench':body={**task,'transcript':None,'versions':[{k:v for k,v in row.items() if k!='content'} for row in task['versions']]}
        elif path.endswith('/transcript'):body={'transcript':task['transcript']};delay=.6
        elif '/versions/' in path:body=task['versions'][0];delay=.6
        elif path=='/api/video-notes/tasks':body={'tasks':[{**task,'markdown':'','transcript':None}]};delay=2.5
        elif path=='/api/summaries/bench':body=summary
        elif path=='/api/notion/pages':body={'pages':[]};delay=.6
        elif path=='/api/library/sources':body={'sources':['Learning lab','Synthetic channel'],'next_cursor':None}
        elif path=='/api/library':
            rows=[{'id':f'episode-{i}','kind':'podcast','title':f'{"New account" if account_changed else "Podcast lesson"} {i}','source':'Learning lab','date':'2026-10-20','status':'completed'} for i in range(85)]
            rows.insert(0,{'id':'bench','kind':'video','title':'Synthetic video','source':'Synthetic channel','date':'2026-10-20','status':'completed'})
            params=parse_qs(urlparse(route.request.url).query)
            q=params.get('q',[''])[0].lower()
            rows=[r for r in rows if q in (r['title']+' '+r['source']).lower()]
            offset=int(params.get('cursor',['0'])[0]); body={'items':rows[offset:offset+40],'next_cursor':str(offset+40) if len(rows)>offset+40 else None}
            if fail_videos:
                await route.fulfill(status=503,body=json.dumps({'detail':'Synthetic library unavailable'}),content_type='application/json');return
        elif path=='/api/summaries':body=[] if empty_podcasts else [{**summary,'podcast_title':'Learning lab','created_at':'2026-10-20','episode_id':f'episode-{i}','title':f'{"New account" if account_changed else "Podcast lesson"} {i}'} for i in range(30)]
        await asyncio.sleep(delay)
        if fail_videos and path == '/api/video-notes/tasks':
            await route.fulfill(status=503,body=json.dumps({'detail':'Synthetic video service unavailable'}),content_type='application/json');return
        await route.fulfill(body=json.dumps(body),content_type='application/json')
    await page.route('**/api/**',api)
    async def image(route):
        images.append(urlparse(route.request.url).path)
        if 'preview=true' not in route.request.url: original_requests.append(urlparse(route.request.url).path)
        await asyncio.sleep(1.2 if route.request.frame.parent_frame else .4)
        await route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#0f172a"/><path d="M0 450 L130 320 L230 380 L420 160 L530 220 L700 80 L960 30" fill="none" stroke="#34d399" stroke-width="6"/><text x="40" y="70" fill="#e2e8f0" font-size="28">Synthetic screenshot — trend review</text></svg>')
    await page.route('**/data/screenshots/**',image)
    result={'label':label,'width':width}
    start=time.monotonic()
    await page.goto(origin+'/library')
    await page.get_by_role('heading',name='Podcast lesson 0',exact=True).wait_for()
    result['library_first_note_ms']=round((time.monotonic()-start)*1000)
    assert not await page.get_by_role('heading',name='Podcast lesson 80',exact=True).count()
    await page.get_by_role('button',name='Show more notes',exact=True).click()
    await page.get_by_role('heading',name='Podcast lesson 70',exact=True).wait_for()
    result['server_pagination']=True
    await page.get_by_role('heading',name='Synthetic video',exact=True).wait_for()
    await page.locator('main').evaluate('(el)=>el.scrollTop=0')
    await page.screenshot(path=str(output/f'{label}-{width}-library.png'))
    await page.get_by_role('button',name='list layout',exact=True).click()
    await page.reload()
    assert await page.get_by_role('button',name='list layout',exact=True).get_attribute('aria-pressed')=='true'
    await page.get_by_role('heading',name='Podcast lesson 0',exact=True).wait_for()
    await page.get_by_label('Search saved notes').fill('missing synthetic title')
    assert await page.get_by_role('heading',name='Podcast lesson 0',exact=True).count()==1
    assert not await page.locator('.animate-pulse').count()
    await page.get_by_role('button',name='Clear filters',exact=True).click()
    await page.wait_for_function("document.querySelector('[aria-label=\"Search saved notes\"]').value === ''")
    if width>=768:
        assert await page.get_by_title('Sign Out',exact=True).is_visible()
    if label == 'after' and width < 1024:
        assert not await page.get_by_label('Podcast or channel',exact=True).is_visible()
        await page.get_by_role('button',name='Filters',exact=True).click()
        assert await page.get_by_label('Podcast or channel',exact=True).is_visible()
        await page.get_by_role('button',name='Filters',exact=True).click()
    result['library_preferences_and_filters']=True
    start=time.monotonic()
    await page.goto(origin+'/videos/bench')
    await page.get_by_role('heading',name='Trading review / 交易复盘',exact=True).wait_for()
    await page.locator('article img').first.wait_for()
    await page.wait_for_function("document.querySelector('article img')?.naturalWidth>0")
    result['note_and_first_image_ms']=round((time.monotonic()-start)*1000)
    result['layout']=await page.evaluate('''()=>{const a=document.querySelector('article').getBoundingClientRect(),c=document.querySelector('#video-content-scroll').getBoundingClientRect();return {article:a.width,content:c.width,viewport:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth}}''')
    await page.screenshot(path=str(output/f'{label}-{width}-note.png'))
    await page.get_by_role('button',name='Export',exact=True).click()
    bounds=await page.locator('.reader-menu-panel').bounding_box()
    assert bounds['x']>=0 and bounds['x']+bounds['width']<=width
    if width<768:
        await page.get_by_role('button',name='Export',exact=True).evaluate('(button)=>button.blur()')
        assert await page.locator('.reader-menu-panel').count()==1
        async with page.expect_download() as pending_download:
            await page.get_by_title('Download .md',exact=True).tap()
        assert (await pending_download.value).suggested_filename.endswith('.md')
        result['touch_export_survives_null_blur']=True
        await page.get_by_role('button',name='Export',exact=True).tap()
    await page.keyboard.press('Escape')
    assert not await page.locator('.reader-menu-panel').count()
    await page.get_by_role('button',name='Reading appearance',exact=True).click()
    await page.get_by_role('group',name='Reading width',exact=True).get_by_role('button',name='Comfortable',exact=True).click()
    assert (await page.locator('article').bounding_box())['width']<=821
    await page.get_by_role('group',name='Reading width',exact=True).get_by_role('button',name='Wide',exact=True).click()
    await page.keyboard.press('Escape')
    if width>1170:
        await page.get_by_role('button',name='Toggle contents',exact=True).click()
        assert not await page.locator('aside[data-reader-contents]').is_visible()
        await page.get_by_role('button',name='Toggle contents',exact=True).click()
    else:
        await page.get_by_role('button',name='Contents',exact=True).click()
        await page.locator('.reader-menu-panel button').first.click()
        await page.locator('main').evaluate('(element)=>element.scrollTop=0')
    result['compact_controls_and_export_bounds']=True
    assert 'preview=true' in await page.locator('article img').first.get_attribute('src')
    await page.locator('article .reader-screenshot').first.click()
    assert 'preview=true' not in await page.get_by_role('dialog',name='Enlarged screenshot').locator('img').get_attribute('src')
    await page.get_by_role('dialog').locator('img').wait_for(state='visible')
    deadline=time.monotonic()+5
    while '/data/screenshots/bench_1.jpg' not in original_requests and time.monotonic()<deadline: await page.wait_for_timeout(50)
    assert '/data/screenshots/bench_1.jpg' in original_requests, 'Adjacent original should prefetch after the current image loads'
    if width<768:
        sizes=await page.get_by_role('dialog').locator('button').evaluate_all('(nodes)=>nodes.map(n=>[n.getBoundingClientRect().width,n.getBoundingClientRect().height])')
        assert all(w>=44 and h>=44 for w,h in sizes),sizes
    await page.get_by_role('button',name='Next',exact=True).click()
    await page.wait_for_function("document.querySelector('[role=dialog] img')?.src.includes('bench_1.jpg')")
    await page.keyboard.press('ArrowLeft')
    await page.wait_for_function("document.querySelector('[role=dialog] img')?.src.includes('bench_0.jpg')")
    await page.get_by_role('button',name='Zoom in',exact=True).click()
    assert await page.get_by_role('button',name='Fit · 150%',exact=True).count()==1
    if width<768:
        await page.get_by_role('button',name='Fit · 150%',exact=True).click()
        bounds=await page.locator('.gallery-viewport').bounding_box()
        x=bounds['x']+bounds['width']/2;y=bounds['y']+min(120,bounds['height']/2)
        def points(distance): return [{'x':x-distance,'y':y,'id':1},{'x':x+distance,'y':y,'id':2}]
        await session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':points(30)})
        await session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':points(60)})
        await session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        await page.wait_for_timeout(100)
        assert not await page.get_by_role('button',name='Fit · 100%',exact=True).count(),'Two-finger pinch should zoom the original'
        result['gallery_touch_zoom_and_adjacent_prefetch']=True
    await page.get_by_role('button',name='Close enlarged screenshot').click()
    result['reading_preferences_and_original_on_demand']=True

    image_count=len(images)
    loaded_paths=set(images)
    start=time.monotonic()
    await page.locator('main').evaluate('(e)=>e.scrollTop=160')
    saved_scroll=await page.locator('main').evaluate('(e)=>e.scrollTop')
    await page.get_by_role('tab',name='Mind map',exact=True).click()
    await page.locator('svg.markmap foreignObject').first.wait_for(timeout=20000)
    result['mindmap_ms']=round((time.monotonic()-start)*1000)
    await page.wait_for_timeout(150)
    group=page.locator('svg.markmap > g').first
    transform=await group.get_attribute('transform')
    await page.get_by_role('button',name=re.compile('zoom in',re.I)).click()
    await page.wait_for_timeout(100)
    result['zoom_changes_transform']=await group.get_attribute('transform')!=transform
    await page.get_by_role('button',name=re.compile('fit to view',re.I)).click()
    await page.screenshot(path=str(output/f'{label}-{width}-mindmap.png'))
    start=time.monotonic()
    await page.get_by_role('tab',name='Summary',exact=True).click()
    await page.locator('article').wait_for(state='visible')
    result['reading_position_retained']=await page.locator('main').evaluate('(e)=>e.scrollTop')>=saved_scroll-1
    result['return_to_note_ms']=round((time.monotonic()-start)*1000)
    result['duplicate_image_requests_after_tab']=sum(path in loaded_paths for path in images[image_count:])
    await page.get_by_role('tab',name='Transcript',exact=True).click()
    await page.get_by_text('Line 00000:',exact=False).first.wait_for()
    await page.get_by_role('tab',name='Summary',exact=True).click()
    copy=page.get_by_role('button',name='Copy note',exact=True)
    if await copy.count():
        await copy.click()
        await page.get_by_role('button',name='Copied',exact=True).wait_for(timeout=10000)
        result['copy_works']=bool(await page.evaluate('navigator.clipboard.readText()'))
    if label == 'after' and width == 1440:
        async def print_spy():
            await page.evaluate("""() => {
              window.__printed = false;
              new MutationObserver(records => records.forEach(r => r.addedNodes.forEach(f => {
                if (f.tagName === 'IFRAME') f.addEventListener('load', () => {
                  f.contentWindow.print = () => { window.__printed = true; f.contentWindow.dispatchEvent(new Event('afterprint')); };
                });
              }))).observe(document.body, {childList:true});
            }""")
        await print_spy()
        await page.get_by_role('button',name='Export',exact=True).click()
        await page.get_by_title('Download PDF',exact=True).click()
        await page.wait_for_timeout(250)
        result['pdf_pending_until_images_load']=await page.get_by_role('button',name='Export',exact=True).get_attribute('aria-busy')=='true'
        assert result['pdf_pending_until_images_load']
        await page.wait_for_function('window.__printed === true',timeout=15000)
        assert await page.get_by_role('button',name='Export',exact=True).get_attribute('aria-busy')=='false'
        if not await page.locator('.reader-menu-panel').count():
            await page.get_by_role('button',name='Export',exact=True).click()
        async with page.expect_download() as pending_download:
            await page.get_by_title('Download .md',exact=True).click()
        result['markdown_download_works']=(await pending_download.value).suggested_filename.endswith('.md')
        if not await page.locator('.reader-menu-panel').count():
            await page.get_by_role('button',name='Export',exact=True).click()
        await page.get_by_title('Send to Notion',exact=True).click()
        await page.get_by_role('dialog',name='Export to Notion').wait_for()
        await page.get_by_role('button',name='Close Notion export',exact=True).first.click()
        result['notion_dialog_works']=not await page.get_by_role('dialog').count()
        assert result['notion_dialog_works'] and result['markdown_download_works']
        await page.goto(origin+'/viewer/bench')
        await page.get_by_role('heading',name='Overview',exact=True).wait_for()
        await page.get_by_role('button',name='Expand all',exact=True).click()
        assert await page.locator('[data-topic-card] button[aria-expanded=false]').count()==0
        await page.get_by_role('button',name='Collapse all',exact=True).click()
        await page.locator('aside[data-reader-contents]').get_by_role('button',name='Measured topic',exact=True).click()
        assert await page.locator('#summary-topic-0 button').get_attribute('aria-expanded')=='true'
        await print_spy()
        await page.get_by_role('button',name='Export',exact=True).click()
        await page.get_by_title('Download PDF',exact=True).click()
        await page.wait_for_function('window.__printed === true' ,timeout=15000)
        result['podcast_pdf_works']=True
        fail_videos=True
        await page.goto(origin+'/library')
        await page.get_by_role('button',name='Refresh library',exact=True).click()
        await page.get_by_text('Synthetic library unavailable',exact=False).wait_for(timeout=10000)
        result['partial_failure_keeps_notes']=await page.get_by_role('heading',name='Podcast lesson 0',exact=True).is_visible()
        assert result['partial_failure_keeps_notes']
        fail_videos=False
    if width==1440:
        empty_podcasts=False
        await page.goto(origin+'/library')
        await page.get_by_role('heading',name='Podcast lesson 0',exact=True).wait_for()
        account_changed=True
        await page.evaluate("""()=>{
          localStorage.setItem('xyz_access_token',NEW_TOKEN);
          localStorage.setItem('xyz_user',JSON.stringify({id:'second',email:'second@example.com',authenticated:true}));
          window.dispatchEvent(new StorageEvent('storage',{key:'xyz_user',storageArea:localStorage}));
        }""".replace('NEW_TOKEN',json.dumps(token(int(time.time())+7200))))
        await page.get_by_role('heading',name='New account 0',exact=True).wait_for()
        assert await page.get_by_role('heading',name='Podcast lesson 0',exact=True).count()==0
        assert await page.get_by_role('button',name='grid layout',exact=True).get_attribute('aria-pressed')=='true'
        result['account_change_remounts_private_page']=True
    result['errors']=errors
    await context.close()
    return result


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--widths',type=int,nargs='+',default=[390,768,1440,1920]);parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);parser.add_argument('--baseline-dist',type=Path);parser.add_argument('--output',type=Path,default=Path('/tmp/xyz-reader-check'));args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    reports=[]
    async with async_playwright() as p:
        for label,dist in [('before',args.baseline_dist),('after',Path(__file__).resolve().parents[1]/'web/dist')]:
            if not dist: continue
            server=serve(dist)
            try:
                for width in args.widths:
                    browser=await p.chromium.launch(executable_path=args.browser_path,headless=True,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
                    report=await check(browser,f'http://127.0.0.1:{server.server_port}',width,args.output,label)
                    reports.append(report);print(json.dumps(report),flush=True)
                    await browser.close()
            finally:server.shutdown()
    (args.output/'results.json').write_text(json.dumps(reports,indent=2))
    for report in reports:
        if report['label']=='after':
            assert not report['errors'],report
            assert not report['layout']['overflow'],report
            assert report['layout']['article'] <= 1121,report
            assert report['layout']['article'] >= min(820, report['layout']['content']-48)*.95,report
            assert report['zoom_changes_transform'] and report.get('copy_works'),report
            assert report['reading_position_retained'],report
            assert report['server_pagination'],report
            assert report['duplicate_image_requests_after_tab']==0,report

if __name__=='__main__':asyncio.run(main())
