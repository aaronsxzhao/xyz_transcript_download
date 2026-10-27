"""Synthetic dashboard pagination, task admission and mobile geometry checks."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve
from scripts.check_page_loading import token
from scripts.check_mobile_controls import AUDIT
from playwright.async_api import async_playwright


async def check(browser, origin, width):
    entries=[{'id':str(i),'kind':'podcast' if i%3==0 else 'video','content_type':'audio' if i%3==0 else 'article' if i%3==1 else 'video',
              'title':f'Synthetic saved content {i:02d} · 一个完整且较长的内容标题，用于验证手机换行和阅读入口',
              'source':'Synthetic source','date':f'2026-10-{27-i:02d}T03:00:00Z','published_at':'2026-09-01',
              'status':'completed','thumbnail':'','platform':'youtube' if i%3==2 else 'substack'} for i in range(18)]
    state={'phase':'discovered','submissions':0,'library_calls':[],'paths':[]}
    def task():
        return {'id':'discovered','title':'Synthetic discovered video','channel':'Synthetic channel','platform':'youtube',
                'url':'https://www.youtube.com/watch?v=abcdefghijk','status':state['phase'],'progress':0,'message':'',
                'markdown':'','transcript':None,'versions':[],'error':'','thumbnail':'','duration':60,'style':'detailed',
                'model':'','formats':['summary'],'created_at':'2026-10-27T03:00:00Z','updated_at':'2026-10-27T03:00:01Z'}
    context=await browser.new_context(viewport={'width':width,'height':900},is_mobile=width<768,has_touch=width<768,service_workers='block')
    await context.add_init_script('''
      localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);
      localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
      window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}
        send(v){if(JSON.parse(v).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),1)}close(){this.readyState=3}}
    '''.replace('TOKEN',json.dumps(token(int(time.time())+7200))))
    async def api(route):
        parsed=urlparse(route.request.url);path=parsed.path;query=parse_qs(parsed.query);body={};state['paths'].append(path)
        if path=='/api/auth/config':body={'supabase_enabled':True}
        elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
        elif path=='/api/stats':body={key:123 for key in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_channels','total_videos','completed_videos']}
        elif path=='/api/library':
            state['library_calls'].append(query)
            kind=query.get('kind',[''])[0]
            rows=[r for r in entries if not kind or kind=='article' and r['content_type']=='article' or kind=='video' and r['kind']=='video' and r['content_type']!='article' or kind=='podcast' and r['kind']=='podcast']
            start=int(query.get('cursor',['0'])[0]);limit=int(query.get('limit',['12'])[0])
            body={'items':rows[start:start+limit],'next_cursor':str(start+limit) if start+limit<len(rows) else None}
        elif path=='/api/content-updates':body={'items':[{'item_key':'video:discovered','kind':'video','title':'Synthetic discovered video','source_title':'Synthetic channel','source_id':'discovered','created_at':'2026-10-27T03:00:00Z'}]}
        elif path=='/api/jobs':body={'jobs':[]}
        elif path=='/api/video-notes/channels':body={'channels':[{'platform':'youtube','channel':'Synthetic channel','total':1,'done':0,'thumbnail':'','channel_avatar':'','channel_url':''}]}
        elif path=='/api/video-notes/tasks/by-channel':body={'tasks':[task()],'next_cursor':None}
        elif path=='/api/video-notes/progress':body={'tasks':[task()] if state['phase']=='pending' else []}
        elif path=='/api/video-notes/tasks/discovered':body=task()
        elif path=='/api/video-notes/tasks/discovered/retry':
            state['submissions']+=1
            await asyncio.sleep(.2)
            state['phase']='pending';body={'task_id':'discovered'}
        elif path=='/api/performance':return await route.fulfill(status=204)
        return await route.fulfill(json=body)
    await context.route('**/api/**',api)
    page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    await page.goto(origin+'/',wait_until='domcontentloaded')
    recent=page.get_by_role('region',name='Recently added')
    await recent.locator('.reading-history-card').nth(11).wait_for()
    assert await recent.locator('.reading-history-card').count()==12
    assert len(state['library_calls'])==1,state['library_calls']
    assert not {'/api/summaries/recent','/api/video-notes/recent'} & set(state['paths'])
    await recent.get_by_role('button',name='Load more',exact=True).click()
    await recent.locator('.reading-history-card').nth(17).wait_for()
    assert await recent.locator('.reading-history-card').count()==18
    await recent.get_by_role('button',name='Articles',exact=True).click()
    await recent.get_by_role('status').filter(has_text='6 loaded').wait_for()
    assert await recent.locator('.reading-history-card').count()==6
    assert await recent.get_by_text('Read article →',exact=True).count()==6
    assert any(q.get('kind')==['article'] for q in state['library_calls'])
    audit=await page.evaluate(AUDIT)
    assert not audit['overflow'] and not audit['problems'],(width,audit)
    if width<768:
        assert await recent.locator('.dashboard-recent-filters button').evaluate_all('(buttons)=>buttons.every(b=>b.getBoundingClientRect().height>=44)')
    assert await page.locator('.dashboard-stats>div').evaluate_all('(cards)=>cards.every(c=>[...c.querySelectorAll("p")].every(p=>p.scrollWidth<=c.clientWidth+1))')
    await page.get_by_role('heading',name='Dashboard',exact=True).scroll_into_view_if_needed()
    await page.screenshot(path=f'/tmp/dashboard-overview-{width}.png')
    await recent.scroll_into_view_if_needed()
    await page.screenshot(path=f'/tmp/dashboard-recent-{width}.png')
    await page.get_by_role('button',name='View new →',exact=True).click()
    discovered=page.get_by_role('dialog').get_by_role('link',name='Synthetic channel Synthetic discovered video')
    assert await discovered.get_attribute('href')=='/videos/discovered'
    await discovered.click()
    await page.get_by_role('heading',name='Not processed yet',exact=True).wait_for()
    await page.get_by_role('button',name='Start processing',exact=True).dblclick()
    await page.get_by_text('Queued',exact=True).first.wait_for()
    assert state['submissions']==1
    await page.goto(origin+'/videos?platform=youtube',wait_until='domcontentloaded')
    channel=page.get_by_role('link').filter(has=page.get_by_role('heading',name='Synthetic channel',exact=True))
    await channel.focus();await page.keyboard.press('Enter')
    await page.wait_for_url('**channel=Synthetic+channel')
    await page.locator('.video-task-list').wait_for()
    audit=await page.evaluate(AUDIT)
    assert not audit['overflow'] and not audit['problems'],(width,audit)
    assert not errors,errors
    print(json.dumps({'width':width,'recent_first_page':12,'recent_more':18,'article_filter':True,'discovered_start':True,'keyboard_channel_navigation':True,'geometry':True,'errors':errors}),flush=True)
    await context.close()


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--widths',type=int,nargs='+',default=[320,390,1440]);args=parser.parse_args()
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            for width in args.widths:await check(browser,f'http://127.0.0.1:{server.server_port}',width)
            await browser.close()
    finally:server.shutdown()


if __name__=='__main__':asyncio.run(main())
