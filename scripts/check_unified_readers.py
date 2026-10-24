"""Exercise dashboard states and versioned mind maps using synthetic API fixtures."""
import argparse,asyncio,json,sys,time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures,serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright

async def check(browser,origin,width,output):
 task,summary=fixtures()
 task.update(title='Bitcoin Daily / Trading review',channel='Trading course',published_at='2026-04-12',model='Test model',formats=['summary','screenshot'],error='')
 task['markdown']='# Trading review\n\nA complete market review.\n\n'+ '\n\n'.join(f'## {i+1}. Market structure\n\nConditional argument {i}. '+('Detailed context. '*40)+f'\n\n- Confirm the signal\n- Manage risk\n\n![Chart](/data/screenshots/bench_{i}.jpg)' for i in range(14))
 summary.update(title='Podcast reading / 播客阅读',overview='### 核心结论\n- Conditional conclusions.\n\n### 节目概览\nA complete overview.',key_points=[{'topic':f'Chapter {i}','summary':'#### Explanation\n\nA complete argument with conditions.\n\n'+('Supporting detail. '*15),'original_quote':'Original transcript evidence.','timestamp':'12:00'} for i in range(7)],topics=[f'Chapter {i}' for i in range(7)])
 state={'jobs':[],'updates':True,'fail_version':False,'completed':False}
 context=await browser.new_context(viewport={'width':width,'height':1000},permissions=['clipboard-read','clipboard-write'],service_workers='block')
 await context.add_init_script('''localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;constructor(){window.fixtureSocket=this;setTimeout(()=>this.onopen?.(),10)}send(v){if(JSON.parse(v).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),5)}close(){this.readyState=3}};window.workerCreates=0;const RealWorker=window.Worker;window.Worker=class extends RealWorker{constructor(...args){super(...args);window.workerCreates++}};'''.replace('TOKEN',json.dumps(token(int(time.time())+7200))))
 page=await context.new_page();errors=[];requests=[]
 page.on('console',lambda message: print('CONSOLE:',message.text[:500],flush=True) if message.type=='error' else None)
 page.on('pageerror',lambda error:(errors.append(str(error)),print('PAGE ERROR:',error,flush=True)))
 async def api(route):
  parsed=urlparse(route.request.url);path=parsed.path;requests.append(path);body={}
  if path=='/api/auth/config':body={'supabase_enabled':True}
  elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
  elif path=='/api/stats':body={'total_podcasts':13,'total_episodes':455,'total_transcripts':108,'total_summaries':96,'total_video_channels':8,'total_videos':216,'completed_videos':42}
  elif path in ['/api/summaries','/api/summaries/recent']:body=[{**summary,'podcast_title':'My podcast','created_at':'2026-10-21','podcast_cover':'','topics_count':7,'title':'Newly completed podcast' if state['completed'] else summary['title']}]
  elif path=='/api/summaries/bench':body=summary
  elif path=='/api/transcripts/bench':body={**task['transcript'],'episode_id':'bench','language':'en'}
  elif path=='/api/video-notes/tasks/bench':body={**task,'transcript':None,'versions':[{k:v for k,v in row.items() if k!='content'} for row in task['versions']]}
  elif path=='/api/video-notes/tasks/bench/transcript':body={'transcript':task['transcript']}
  elif '/versions/' in path:
   if state['fail_version']:
    await route.fulfill(status=503,body=json.dumps({'detail':'Version unavailable'}),content_type='application/json');return
   version=next(v for v in task['versions'] if v['id']==path.rsplit('/',1)[-1]);body={**version,'content':f'# Saved version {version["id"]}\n\n## Saved chapter\n\nSaved argument.'};await asyncio.sleep(.25)
  elif path in ['/api/video-notes/tasks','/api/video-notes/tasks/recent','/api/video-notes/recent']:body={'tasks':[task]}
  elif path=='/api/video-notes/progress':body={'tasks':[]}
  elif path=='/api/jobs':body={'jobs':state['jobs']}
  elif path=='/api/content-updates':body={'items':[{'item_key':'podcast:one','kind':'podcast','source_id':'show','source_title':'My podcast','title':'New episode','created_at':'2026-10-22T00:00:00Z'}] if state['updates'] else [],'dismiss_before':'2026-10-22T00:00:00Z'}
  elif path=='/api/content-updates/dismiss':state['updates']=False;body={'ok':True}
  elif path=='/api/library':body={'items':[],'next_cursor':None}
  await route.fulfill(body=json.dumps(body),content_type='application/json')
 await page.route('**/api/**',api)
 await page.route('**/data/**',lambda route:route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#162838"/><path d="M10 480 L180 360 L300 400 L520 180 L700 240 L950 40" fill="none" stroke="#5bd8b0" stroke-width="6"/></svg>'))
 await page.goto(origin+'/')
 await page.locator('.dashboard-idle').wait_for(timeout=10000)
 assert not await page.locator('.dashboard-processing').count()
 await page.get_by_role('button',name='Task history →',exact=True).click()
 await page.get_by_role('dialog',name='Task history').wait_for()
 await page.keyboard.press('Escape')
 await page.get_by_role('button',name='View new →',exact=True).click()
 await page.get_by_role('dialog',name='New content',exact=True).wait_for()
 assert await page.get_by_text('New episode',exact=True).count()==1
 await page.keyboard.press('Escape')
 await page.screenshot(path=str(output/f'dashboard-idle-{width}.png'))
 job={'job_id':'active','episode_id':'new','episode_title':'Processing podcast','status':'transcribing','progress':42,'message':'Transcribing audio','started_at':time.time()-60}
 await page.evaluate('job=>window.fixtureSocket.onmessage({data:JSON.stringify({type:"init",jobs:[job],video_tasks:[]})})',job)
 await page.locator('.dashboard-processing').wait_for()
 await page.screenshot(path=str(output/f'dashboard-active-{width}.png'))
 assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
 before_refresh=requests.count('/api/stats')
 state['completed']=True
 await page.evaluate('job=>window.fixtureSocket.onmessage({data:JSON.stringify({type:"job_update",job:{...job,status:"completed",progress:100}})})',job)
 await page.get_by_role('heading',name='Newly completed podcast',exact=True).wait_for()
 assert requests.count('/api/stats')>before_refresh
 assert not await page.locator('.dashboard-processing').count()
 await page.goto(origin+'/viewer/bench')
 await page.get_by_role('heading',name='Podcast reading / 播客阅读',exact=True).wait_for()
 await page.get_by_role('tab',name='Summary',exact=True).click()
 assert await page.locator('.topic-content').count()==7
 await page.get_by_role('button',name='Reading appearance',exact=True).click()
 await page.get_by_role('group',name='Text size',exact=True).get_by_role('button',name='18',exact=True).click()
 await page.get_by_role('group',name='Reading width',exact=True).get_by_role('button',name='Wide',exact=True).click()
 assert await page.locator('.reader-menu-panel').is_visible()
 await page.keyboard.press('Escape')
 assert await page.locator('.podcast-reader').evaluate('element=>getComputedStyle(element).fontSize')=='18px'
 await page.get_by_role('button',name='More summary actions').click()
 await page.get_by_role('button',name='Regenerate summary',exact=True).click()
 await page.get_by_role('dialog',name='Regenerate summary',exact=True).wait_for()
 await page.get_by_role('button',name='Cancel',exact=True).click()
 await page.keyboard.press('Escape')
 assert not any('/resummarize' in path for path in requests)
 await page.screenshot(path=str(output/f'podcast-{width}.png'))
 await page.goto(origin+'/videos/bench')
 await page.locator('article img').first.wait_for()
 await page.screenshot(path=str(output/f'video-{width}.png'))
 await page.get_by_role('button',name='Export',exact=True).click()
 assert await page.get_by_title('Download .md',exact=True).is_visible()
 await page.keyboard.press('Escape')
 start=time.monotonic()
 await page.get_by_role('tab',name='Mind map',exact=True).click()
 await page.locator('svg.markmap foreignObject').first.wait_for(timeout=20000)
 await page.wait_for_function('document.querySelector(".mindmap-canvas").getAttribute("aria-busy")==="false"')
 first_ms=round((time.monotonic()-start)*1000)
 assert await page.evaluate('window.workerCreates')==1
 await page.screenshot(path=str(output/f'mindmap-{width}.png'))
 transform=await page.locator('svg.markmap>g').first.get_attribute('transform')
 await page.get_by_role('button',name='Zoom in',exact=True).click()
 await page.wait_for_timeout(100)
 assert await page.locator('svg.markmap>g').first.get_attribute('transform')!=transform
 await page.get_by_role('button',name='Fit to view',exact=True).click()
 async with page.expect_download() as download:
  await page.get_by_role('button',name='Export SVG',exact=True).click()
 assert (await download.value).suggested_filename=='mindmap.svg'
 for _ in range(3):
  await page.get_by_role('tab',name='Summary',exact=True).click()
  await page.get_by_role('tab',name='Mind map',exact=True).click()
  await page.wait_for_function('document.querySelector(".mindmap-canvas").getAttribute("aria-busy")==="false"')
 assert await page.evaluate('window.workerCreates')==1
 await page.reload()
 await page.get_by_role('tab',name='Mind map',exact=True).click()
 await page.locator('svg.markmap foreignObject').first.wait_for()
 assert await page.evaluate('window.workerCreates')==0,'Reload should use IndexedDB outline, not rebuild it'
 await page.get_by_role('button',name='More summary actions').click()
 await page.get_by_role('button',name='Version history',exact=True).click()
 await page.get_by_label('Note version',exact=True).select_option('v0')
 await page.wait_for_function('document.querySelector("svg.markmap")?.textContent.includes("Saved version v0")')
 assert await page.evaluate('window.workerCreates')==1
 await page.get_by_label('Note version',exact=True).select_option('')
 await page.wait_for_function('document.querySelector("svg.markmap")?.textContent.includes("Trading review")')
 assert await page.evaluate('window.workerCreates')==1
 if width==1440:
  # Cache identity follows exact worker input, including image query changes.
  # Rebuild changed source, then reuse that exact source after another reload.
  task['markdown']=task['markdown'].replace('.jpg)', '.jpg?token=fresh)')
  task['title']='Updated screenshot signatures'
  await page.reload()
  await page.get_by_role('heading',name=task['title'],exact=True).wait_for()
  await page.get_by_role('tab',name='Mind map',exact=True).click()
  await page.locator('svg.markmap foreignObject').first.wait_for()
  await page.wait_for_function('document.querySelector(".mindmap-canvas").getAttribute("aria-busy")==="false"')
  assert await page.evaluate('window.workerCreates')==1,'Changed Markdown must not reuse an outline for different source'
  await page.reload()
  await page.get_by_role('heading',name=task['title'],exact=True).wait_for()
  await page.get_by_role('tab',name='Mind map',exact=True).click()
  await page.locator('svg.markmap foreignObject').first.wait_for()
  assert await page.evaluate('window.workerCreates')==0,'Unchanged Markdown should reuse the persisted outline'
  task.update(title='Screenshot warning',error='Some screenshots are unavailable.')
  await page.reload()
  await page.locator('.unified-header').get_by_role('heading',name='Screenshot warning',exact=True).wait_for()
  await page.get_by_role('button',name='Review screenshots',exact=True).click()
  await page.get_by_role('button',name='Repair screenshots',exact=True).wait_for()
  await page.get_by_role('button',name='Close details',exact=True).click()
  task['error']=''
  # A broken worker fetch must become a recoverable error, never an endless spinner.
  task['markdown']='# Retry coverage\n\n## A chapter\n\nA complete argument.'
  task['title']='Retry coverage'
  await context.route('**/assets/mindmap.worker-*.js',lambda route:route.abort())
  await page.reload()
  await page.locator('.unified-header').get_by_role('heading',name='Retry coverage',exact=True).wait_for()
  await page.get_by_role('tab',name='Mind map',exact=True).click()
  await page.get_by_role('button',name='Retry mind map',exact=True).wait_for()
  await context.unroute('**/assets/mindmap.worker-*.js')
  await page.get_by_role('button',name='Retry mind map',exact=True).click()
  await page.locator('svg.markmap foreignObject').first.wait_for()
  await page.wait_for_function('document.querySelector(".mindmap-canvas").getAttribute("aria-busy")==="false"')
  task.update(markdown='',title='Empty saved note')
  await page.reload()
  await page.get_by_role('heading',name='Empty saved note',exact=True).wait_for()
  await page.get_by_role('tab',name='Mind map',exact=True).click()
  await page.get_by_role('heading',name='No summary to map yet',exact=True).wait_for()
  assert await page.evaluate('window.workerCreates')==0
 assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
 assert not errors,errors
 print(json.dumps({'width':width,'first_mindmap_ms':first_ms,'dashboard_idle_active':'passed','reader_actions':'passed','map_zoom_export':'passed','map_revisit_and_disk_cache':'passed','map_version_switch':'passed','errors':errors}),flush=True)
 await context.close()

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--browser-args',type=Path);parser.add_argument('--widths',nargs='+',type=int,default=[1440,768,390]);parser.add_argument('--output',type=Path,default=Path('/tmp/xyz-unified-readers'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 server=serve(Path(__file__).resolve().parents[1]/'web/dist')
 try:
  async with async_playwright() as p:
   for width in args.widths:
    browser=await p.chromium.launch(executable_path=args.browser_path,args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
    try:await check(browser,f'http://127.0.0.1:{server.server_port}',width,args.output)
    finally:await browser.close()
 finally:server.shutdown()
if __name__=='__main__':asyncio.run(main())
