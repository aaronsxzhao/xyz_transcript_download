"""Synthetic mobile control geometry and interaction checks; no private data."""
import sys,asyncio,json,time,argparse
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve,fixtures
from scripts.check_page_loading import token
from playwright.async_api import async_playwright
AUDIT=r'''() => {
 const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'};
 const problems=[];
 for(const b of document.querySelectorAll('button,a.ui-button,[data-account-status]')){
  if(!visible(b))continue;
  const r=b.getBoundingClientRect(), label=b.getAttribute('aria-label')||b.textContent.trim()||b.title;
  const icons=[...b.querySelectorAll('svg')].filter(visible);
  if(!b.textContent.trim()&&icons.length===1){const s=icons[0].getBoundingClientRect();const dx=(s.x+s.width/2)-(r.x+r.width/2),dy=(s.y+s.height/2)-(r.y+r.height/2);if(Math.abs(dx)>2||Math.abs(dy)>2)problems.push({kind:'icon',label,dx,dy,css:b.className});}
  const w=document.createTreeWalker(b,NodeFilter.SHOW_TEXT);let n;
  while(n=w.nextNode()){if(!n.textContent.trim()||!visible(n.parentElement))continue;let clipped=false;for(let e=n.parentElement;e&&e!==b;e=e.parentElement){if(getComputedStyle(e).overflow==='hidden')clipped=true;}if(clipped)continue;const range=document.createRange();range.selectNodeContents(n);for(const t of range.getClientRects()){if(t.width&&t.height&&(t.left<r.left-1||t.right>r.right+1||t.top<r.top-1||t.bottom>r.bottom+1))problems.push({kind:'text',label,text:n.textContent.trim(),button:[r.x,r.y,r.width,r.height],textBounds:[t.x,t.y,t.width,t.height],css:b.className});}}
 }
 return {problems,overflow:document.querySelector('main')?.scrollWidth>document.querySelector('main')?.clientWidth+1,shellFits:Math.abs(document.querySelector('.app-shell').getBoundingClientRect().height-innerHeight)<=1};
}'''
async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true');parser.add_argument('--widths',type=int,nargs='+',default=[320,360,390,430,1440]);parser.add_argument('--output',type=Path,default=Path('/tmp/xyz-mobile-controls'));args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 server=serve(Path(__file__).resolve().parents[1]/'web/dist');origin=f'http://127.0.0.1:{server.server_port}'
 task,summary=fixtures();task['versions']=[]
 settings={'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq','llm_model':'openai/gpt-oss-120b','check_interval':3600,'groq_available':True}
 async with async_playwright() as p:
  browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
  for width in args.widths:
   context=await browser.new_context(viewport={'width':width,'height':844},is_mobile=width<768,has_touch=width<768,service_workers='block')
   await context.add_init_script("localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+7200))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[{job_id:'fixture-job',episode_title:'A long podcast title / 一期较长的播客标题',status:'failed',progress:0,message:'Connection needs attention'}],video_tasks:[]})}),1)}close(){}}")
   page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   connection_offline=False
   connection_reads={'/api/auth/me':0,'/api/library':0}
   async def inspect(label):
    result=await page.evaluate(AUDIT)
    assert not result['problems'],(width,label,result['problems'])
    assert not result['overflow'],(width,label,'horizontal overflow')
    assert result['shellFits'],(width,label,'viewport height mismatch')
    return result
   async def api(route):
    path=urlparse(route.request.url).path;body={}
    if path in connection_reads:
     connection_reads[path]+=1
     if connection_offline:
      await route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Service temporarily unavailable'}))
      return
    if path=='/api/auth/config':body={'supabase_enabled':True}
    elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
    elif path=='/api/settings':body=settings
    elif path=='/api/cookies':body={'cookies':[{'platform':'bilibili','has_cookie':True},{'platform':'youtube','has_cookie':True}]}
    elif path=='/api/settings/models':body={'models':['fixture-model']}
    elif path=='/api/cookies/douyin/diagnose':body={'has_cookie':False,'looks_usable':False,'message':'No saved cookies','present':[],'missing':[],'cookie_count':0,'domains':[]}
    elif path=='/api/stats':body={k:12 for k in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_channels','total_videos','completed_videos']}
    elif path=='/api/summaries/bench':body=summary
    elif path=='/api/video-notes/tasks/bench':body=task
    elif path in ['/api/summaries/recent','/api/podcasts']:body=[]
    elif path=='/api/jobs':body={'jobs':[{'job_id':'fixture-job','episode_title':'A long podcast title / 一期较长的播客标题','status':'failed','progress':0,'message':'Connection needs attention'}]}
    elif path=='/api/content-updates':body={'items':[]}
    elif path=='/api/video-notes/channels':body={'channels':[{'platform':platform,'channel':f'{platform}-{i}','total':total,'done':done,'channel_avatar':'','thumbnail':'','channel_url':'','last_updated':''} for platform,count,total,done in [('bilibili',12,17,2),('youtube',4,34,5),('local',1,2,2)] for i in range(count)]}
    elif path=='/api/library':body={'items':[],'next_cursor':None}
    elif path.startswith('/api/video-notes/'):body={'tasks':[]}
    await route.fulfill(content_type='application/json',body=json.dumps(body))
   await page.route('**/api/**',api)
   # One retry must recover the session and page together, without adding a
   # second viewport above the app or requiring two independent retry buttons.
   connection_offline=True
   await page.goto(origin+'/library',wait_until='networkidle')
   await page.locator('.connection-notice').wait_for()
   await page.get_by_role('button',name='Retry',exact=True).wait_for()
   await inspect('connection-failure')
   await page.screenshot(path=str(args.output/f'connection-{width}.png'))
   connection_offline=False
   await page.get_by_role('button',name='Retry connection',exact=True).click()
   await page.get_by_text('No matching notes',exact=True).wait_for()
   assert not await page.locator('.connection-notice,[role=alert]').count()
   assert list(connection_reads.values())==[3,3],connection_reads
   if width==390:
    for event in ['online','visibilitychange']:
     connection_offline=True
     await page.goto(origin+'/library?q='+event,wait_until='networkidle')
     await page.locator('.connection-notice').wait_for()
     await page.get_by_role('button',name='Retry',exact=True).wait_for()
     connection_offline=False
     if event=='visibilitychange':
      before=dict(connection_reads)
      await page.evaluate("Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'))")
      await page.wait_for_timeout(100)
      assert connection_reads==before,connection_reads
      await page.evaluate("Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});document.dispatchEvent(new Event('visibilitychange'))")
     else:
      await page.evaluate("dispatchEvent(new Event('online'))")
     await page.get_by_text('No matching notes',exact=True).wait_for()
     assert not await page.locator('.connection-notice,[role=alert]').count()
     if event=='visibilitychange':await page.evaluate("delete document.visibilityState")
   for path in ['/','/library','/podcasts','/videos','/settings','/viewer/bench','/videos/bench']:
    await page.goto(origin+path,wait_until='networkidle')
    await inspect(path)
    if path=='/':
     await page.get_by_role('button',name='Open processing tasks',exact=True).click()
     await page.get_by_role('dialog',name='Processing tasks',exact=True).wait_for()
     await inspect('processing')
     await page.get_by_role('button',name='Close processing tasks',exact=True).click()
     if width<768:
      await page.get_by_role('button',name='Open navigation',exact=True).click()
      await inspect('navigation')
      await page.evaluate("history.pushState({},'', '/library');dispatchEvent(new PopStateEvent('popstate'))")
      await page.get_by_role('button',name='Open navigation',exact=True).wait_for()
      assert await page.get_by_role('button',name='Open navigation',exact=True).get_attribute('aria-expanded')=='false'
    if path=='/podcasts':
     await page.get_by_role('button',name='Add Podcast',exact=True).click()
     await inspect('add-podcast')
    if path=='/videos':
     cards=page.locator('.platform-overview-card')
     assert await cards.count()==3
     for card in await cards.all():
      result=await card.evaluate("""el=>{const title=el.querySelector('h3'),row=el.children[0].getBoundingClientRect(),stats=el.children[1].getBoundingClientRect();return {singleLine:title.getBoundingClientRect().height<=parseFloat(getComputedStyle(title).lineHeight)+1,stacked:stats.top>=row.bottom-1,contained:el.scrollWidth<=el.clientWidth+1}}""")
      assert all(result.values()),(width,result)
     await page.screenshot(path=str(args.output/f'platforms-{width}.png'))
    if path=='/settings':
     await page.get_by_label('Summary provider',exact=True).select_option('custom')
     await page.get_by_label('Summary Base URL',exact=True).wait_for()
     await inspect('custom-models')
     await page.get_by_role('button',name='Platform Accounts',exact=True).click()
     await inspect('accounts')
     for platform in ['BiliBili','YouTube','Douyin','Kuaishou']:
      button=page.get_by_role('button',name=platform,exact=True)
      try:
       await button.click(timeout=5000)
      except Exception:
       await page.screenshot(path=str(args.output/'failure.png'))
       print(json.dumps({'errors':errors,'body':(await page.locator('body').inner_text())[:1800]}),flush=True)
       raise
      assert await button.get_attribute('aria-pressed')=='true'
     await page.screenshot(path=str(args.output/f'accounts-{width}.png'))
     await page.add_style_tag(content='.app-shell button, .ui-scope button { font-size:18px !important; }')
     await inspect('enlarged-account-controls')
    if path=='/videos/bench':
     await page.get_by_role('button',name='More summary actions',exact=True).click()
     await inspect('reader-actions')
     await page.keyboard.press('Escape')
     await page.get_by_role('button',name='Reading appearance',exact=True).click()
     await inspect('appearance')
     await page.screenshot(path=str(args.output/f'reader-{width}.png'))
     # Readable enlarged labels must fit too, not be hidden behind clipping.
     await page.add_style_tag(content='.app-shell button, .ui-scope button { font-size:18px !important; }')
     await inspect('enlarged-controls')
   assert not errors,errors
   print(json.dumps({'width':width,'engine':'webkit' if args.webkit else 'chromium','button_text_contained':True,'icons_centered':True,'settings_and_reader_menus':True,'navigation_closes_on_route_change':width<768,'errors':errors}),flush=True)
   await context.close()
  await browser.close()
 server.shutdown()
asyncio.run(main())
