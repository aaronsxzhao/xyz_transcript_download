"""Synthetic grouped-task, mobile drawer and failure visibility checks."""
import sys,json,asyncio,time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright
jobs=[dict(job_id='p'+str(i),episode_id=f'{i:024x}',episode_title=title,status=status,progress=pct,message=msg) for i,(title,status,pct,msg) in enumerate([
('量化交易：如何建立稳定的执行系统','transcribing',48,'Transcribing with Whisper…'),
('长期投资与风险管理','pending',0,'Queued for processing…'),
('宏观经济与资产配置','summarizing',76,'Summarizing chunk 2/8…'),
('2026 年三季度复盘','failed',30,'Audio source is restricted. Purchase required.'),
('如何避免过度交易','completed',100,'Summary saved successfully'),
])]
tasks=[dict(id='v'+str(i),title=title,status=status,progress=pct,message=msg,platform='youtube',channel='Trading Course',url='https://youtube.com/watch?v=fixture',created_at='2026-10-21',published_at='2026-10-20',duration=1200,thumbnail='',style='detailed',formats=['summary'],markdown='',error=msg if status=='failed' else '') for i,(title,status,pct,msg) in enumerate([
('Price action analysis: trading range and breakouts','saving',98,'Saving notes and screenshots…'),
('Bitcoin daily trading range','pending',0,'Queued for processing…'),
('S&P500 E-mini market structure review','downloading',22,'Downloading audio…'),
('Support and resistance','failed',45,'Transcription request timed out'),
])]
async def main():
 server=serve(Path('web/dist').resolve()); origin=f'http://127.0.0.1:{server.server_port}'
 async with async_playwright() as p:
  launch={}
  if Path('/usr/bin/chromium').exists():launch={'executable_path':'/usr/bin/chromium','args':['--no-sandbox']}
  if Path('/tmp/chromium').exists():launch={'executable_path':'/tmp/chromium','args':json.loads(Path('/tmp/xyz-chromium-args.json').read_text())}
  for width in [1440,390]:
   tasks[0].update(status="saving",progress=98,markdown="",updated_at='2026-10-21T14:59:59Z')
   detail_reads=0
   browser=await p.chromium.launch(**launch)
   context=await browser.new_context(viewport={'width':width,'height':960},service_workers='block')
   init={'type':'init','jobs':jobs,'video_tasks':tasks}
   await context.add_init_script("""localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;constructor(){window.__auditSocket=this;setTimeout(()=>this.onopen?.(),10)}send(value){if(JSON.parse(value).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify(INIT)}),10)}close(){this.readyState=3}};""".replace('TOKEN',json.dumps(token(int(time.time())+3600))).replace('INIT',json.dumps(init)))
   page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   async def api(route):
    nonlocal detail_reads
    path=urlparse(route.request.url).path;body={}
    if path=='/api/auth/config':body={'supabase_enabled':True}
    elif path=='/api/auth/me':body={'id':'bench','email':'','authenticated':True}
    elif path=='/api/stats':body={k:12 for k in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_tasks','completed_video_tasks']}
    elif path=='/api/content-updates':body={'items':[]}
    elif path=='/api/jobs':body={'jobs':jobs}
    elif path=='/api/summaries/recent':body=[]
    elif path in ['/api/video-notes/tasks','/api/video-notes/progress','/api/video-notes/tasks/recent','/api/video-notes/recent','/api/video-notes/tasks/by-channel']:body={'tasks':tasks,'next_cursor':None}
    elif path=='/api/video-notes/channels':body={'channels':[{'channel':'Trading Course','platform':'youtube','total_count':4,'success_count':0,'processing_count':3,'failed_count':1,'channel_avatar':'','total':4,'done':0}]}
    elif path=='/api/library/sources':body={'sources':[],'next_cursor':None}
    elif path=='/api/library':body={'items':[],'next_cursor':None}
    elif path=='/api/video-notes/tasks/v0':
     detail_reads+=1;body=tasks[0]
    elif path=='/api/health':body={'revision':'audit'}
    await route.fulfill(content_type='application/json',body=json.dumps(body))
   await page.route('**/api/**',api)
   await page.goto(origin+'/',wait_until='domcontentloaded');await page.locator('.dashboard-stats').wait_for();await page.get_by_role('button',name='Open processing tasks',exact=True).wait_for(timeout=10000)
   assert not await page.get_by_role('dialog',name='Processing tasks').count()
   await page.get_by_role('button',name='Open processing tasks',exact=True).click()
   drawer=page.get_by_role('dialog',name='Processing tasks')
   await drawer.wait_for()
   assert await drawer.locator('[role=progressbar]').count()==4
   assert not await drawer.locator('[data-task-id=p1] [role=progressbar]').count()
   assert await drawer.get_by_text('4 processing · 2 queued · 2 need attention',exact=True).count()==1
   assert await drawer.get_by_role('link',name='Open original episode').count()==1
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   await page.screenshot(path=f'/tmp/task-drawer-{width}.png')
   await page.keyboard.press('Escape')
   assert not await page.get_by_role('dialog',name='Processing tasks').count()
   await page.screenshot(path=f'/tmp/audit-dashboard-{width}.png')
   print(json.dumps({'viewport':width,'overflow':await page.evaluate('document.documentElement.scrollWidth>innerWidth'),'errors':errors}),flush=True)
   await page.locator('.dashboard-processing').scroll_into_view_if_needed();await page.screenshot(path=f'/tmp/audit-queue-{width}.png')
   await page.goto(origin+'/videos?platform=youtube&channel=Trading+Course',wait_until='domcontentloaded');await page.get_by_role('heading',name='Trading Course',exact=True).wait_for();await page.screenshot(path=f'/tmp/audit-videos-{width}.png')
   await page.goto(origin+'/videos/v0',wait_until='domcontentloaded')
   await page.get_by_text('Saving and verifying',exact=True).first.wait_for()
   before_reads=detail_reads
   await page.wait_for_timeout(3500)
   assert detail_reads==before_reads==1, detail_reads
   tasks[0].update(status='success',progress=100,markdown='# Finished note\n\nCompleted task content.',updated_at='2026-10-21T15:00:00Z')
   await page.evaluate("task=>window.__auditSocket.onmessage({data:JSON.stringify({type:'video_job_update',task})})",tasks[0])
   await page.get_by_text('Completed task content.',exact=True).first.wait_for()
   assert detail_reads==2,detail_reads
   # A second processing cycle must refresh the note and its already-open map,
   # even though the original note and the final task both say success.
   await page.get_by_role('tab',name='Mind map',exact=True).click()
   await page.locator('svg.markmap foreignObject').first.wait_for(timeout=20000)
   tasks[0].update(status='transcribing',progress=45,updated_at='2026-10-21T15:00:01Z')
   await page.evaluate("task=>window.__auditSocket.onmessage({data:JSON.stringify({type:'video_job_update',task})})",tasks[0])
   await page.get_by_text('A new version is processing. Showing the saved note.',exact=True).wait_for()
   tasks[0].update(status='success',progress=100,markdown='# Revised after external regeneration\n\nUpdated full note content.',updated_at='2026-10-21T15:00:02Z')
   await page.evaluate("task=>window.__auditSocket.onmessage({data:JSON.stringify({type:'video_job_update',task})})",tasks[0])
   await page.locator('svg.markmap foreignObject').filter(has_text='Revised after external regeneration').first.wait_for(timeout=20000)
   await page.get_by_role('tab',name='Summary',exact=True).click()
   await page.get_by_text('Updated full note content.',exact=True).first.wait_for()
   assert detail_reads==3,detail_reads
   for _ in range(2):
    await page.get_by_role('button',name='Open processing tasks',exact=True).click()
    drawer=page.get_by_role('dialog',name='Processing tasks')
    await drawer.locator('[data-task-id=v0]').get_by_role('link',name='Read summary',exact=True).click()
    await drawer.wait_for(state='detached')
    await page.get_by_text('Updated full note content.',exact=True).first.wait_for()
   await page.screenshot(path=f'/tmp/task-summary-navigation-{width}.png')
   assert not errors,errors
   print(json.dumps({'viewport':width,'detail_reads_while_processing':before_reads,'detail_reads_after_completion':detail_reads,'drawer_grouped':True}),flush=True)
   await browser.close()
 server.shutdown()
asyncio.run(main())
