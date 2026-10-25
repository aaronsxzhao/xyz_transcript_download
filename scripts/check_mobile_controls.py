"""Synthetic mobile control geometry and interaction checks; no private data."""
import sys,asyncio,json,time,argparse,io,zipfile
from pathlib import Path
from urllib.parse import urlparse,parse_qs
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
 archive_stream=io.BytesIO()
 with zipfile.ZipFile(archive_stream,'w',zipfile.ZIP_DEFLATED) as archive:
  archive.writestr('note.md','# Synthetic archive\n\n原始文字完整保留。')
  archive.writestr('images/chart.bin',bytes(range(256)))
 archive_bytes=archive_stream.getvalue()
 settings={'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq','llm_model':'openai/gpt-oss-120b','check_interval':3600,'groq_available':True}
 async with async_playwright() as p:
  browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
  for width in args.widths:
   settings.update(llm_model='openai/gpt-oss-120b',llm_provider='groq',whisper_model='whisper-large-v3')
   holds={'read':None,'save':None,'test':None,'notion':None}
   notion={'failed':False,'submitted':0}
   episode_state={'metadata':None,'one':None,'two':None,'submitted':[],'uploads':0}
   social_state={'library':False,'submitted':[]}
   social_markdown='# Original public article\n\nAuthor: Synthetic writer\n\n[Original source](https://writer.substack.com/p/public)\n\n## Table of Contents\n- [Original heading](#original-heading)\n\n## Original heading\n\nFirst original paragraph.\n\n### 2.1 #### Literal source heading\n\nFull final original paragraph. 原文末段完整保留。'
   long_caption='Synthetic chart explanation · '+('LongUnbrokenCaption'*80)
   screenshot_markdown='# Screenshot review\n\n![Missing chart](/data/screenshots/fixture-missing.jpg)\n\n!['+long_caption+'](https://images.example.test/landscape.svg)\n\n![Portrait chart](https://images.example.test/portrait.svg)'
   maintenance={'empty':False,'bundle_requests':0}
   context=await browser.new_context(viewport={'width':width,'height':844},is_mobile=width<768,has_touch=width<768,service_workers='block')
   await context.add_init_script("localStorage.setItem('xyz_access_token',"+json.dumps(token(int(time.time())+7200))+");localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[{job_id:'fixture-job',episode_title:'A long podcast title / 一期较长的播客标题',status:'failed',created_at:1700000000,progress:0,message:'Connection needs attention'}],video_tasks:[]})}),1)}close(){}}")
   page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   connection_offline=False
   connection_reads={'/api/auth/me':0,'/api/library':0}
   async def inspect(label):
    await page.evaluate("async()=>{await Promise.all(document.querySelector('.toast-stack')?.getAnimations({subtree:true}).map(animation=>animation.finished.catch(()=>{}))||[])}")
    result=await page.evaluate(AUDIT)
    assert not result['problems'],(width,label,result['problems'])
    assert not result['overflow'],(width,label,'horizontal overflow')
    assert result['shellFits'],(width,label,'viewport height mismatch')
    assert await page.evaluate("()=>[...document.querySelectorAll('.toast-stack p')].every(el=>el.scrollWidth<=el.clientWidth+1)"),(width,label,'notification text overflow')
    assert await page.evaluate("()=>{const el=document.querySelector('.toast-stack'),r=el?.getBoundingClientRect();return !r||!el.children.length||(r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1)}"),(width,label,'notifications outside viewport')
    return result
   async def api(route):
    path=urlparse(route.request.url).path;body={}
    if path=='/api/maintenance/notes/screenshots/bundle':
     maintenance['bundle_requests']+=1
     if maintenance['bundle_requests']==1:
      await route.fulfill(content_type='text/html',body='<html>Temporary proxy error</html>')
     else:
      await route.fulfill(content_type='application/zip',headers={'X-Missing-Images':'0'},body=archive_bytes)
     return
    if path in connection_reads:
     connection_reads[path]+=1
     if connection_offline:
      await route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Service temporarily unavailable'}))
      return
    if path=='/api/auth/config':body={'supabase_enabled':True}
    elif path=='/api/auth/me':body={'id':'bench','email':'bench@example.com','authenticated':True}
    elif path=='/api/settings':
     if route.request.method=='POST':
      settings.update(route.request.post_data_json)
      body={'message':'Saved','settings':dict(settings)}
      if holds['save']:await holds['save'].wait()
     else:
      body=dict(settings)
      if holds['read']:await holds['read'].wait()
    elif path=='/api/settings/test-llm':
     body={'message':'Connected','model':route.request.post_data_json['llm_model']}
     if holds['test']:await holds['test'].wait()
    elif path=='/api/truncated':body={'truncated':[] if maintenance['empty'] else [{'episode_id':'reviewed','episode_title':'Synthetic incomplete transcript','episode_duration':100,'transcript_duration':20,'percentage':20}]}
    elif path=='/api/truncated/cleanup':
     assert route.request.post_data_json=={'episode_ids':['reviewed']}
     await route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Synthetic cleanup unavailable'}))
     return
    elif path=='/api/notion/pages':body={'pages':[{'id':str(i),'title':f'Synthetic notebook {i} · 一个较长的笔记本名称','icon':'📄','url':'https://notion.so/target'} for i in range(12)]}
    elif path=='/api/notion/export-markdown':
     notion['submitted']+=1
     assert route.request.post_data_json['markdown'].strip()
     if holds['notion']:await holds['notion'].wait()
     if notion['failed']:
      await route.fulfill(status=502,content_type='application/json',body=json.dumps({'detail':'Notion page was created at https://notion.so/'+('created-page-'*12)+', but content upload was not completed. Check this page before exporting again.'}))
      return
     body={'title':'Synthetic saved note','page_id':'created','url':'https://notion.so/created'}
    elif path in ['/api/podcasts/fixture-source','/api/podcasts/fixture-local']:
     if path.endswith('fixture-source') and episode_state['metadata']:await episode_state['metadata'].wait()
     body={'pid':path.rsplit('/',1)[1],'title':'Synthetic source · 一个较长的播客名称','platform':'local' if path.endswith('fixture-local') else 'apple','episode_count':3,'summarized_count':1}
    elif path=='/api/podcasts/content':
     pid=parse_qs(urlparse(route.request.url).query)['pid'][0]
     body=[{'eid':eid,'pid':pid,'title':'Synthetic episode '+eid+' · 播客标题与处理状态测试','duration':5100,'pub_date':'2026-10-23','created_at':'2026-10-24','source_status':'','has_summary':eid=='ready','has_transcript':eid=='ready','topics_count':28,'key_points_count':42} for eid in ['one','two','ready']]
    elif path=='/api/process':
     source=route.request.post_data_json['episode_url'];episode_state['submitted'].append(source)
     eid=source.split('://',1)[1]
     if episode_state[eid]:await episode_state[eid].wait()
     body={'job_id':'episode-'+eid}
    elif path=='/api/podcasts/upload-audio':
     episode_state['uploads']+=1
     await route.fulfill(status=422,content_type='application/json',body=json.dumps({'detail':'Synthetic audio format rejected: https://source.example/'+('audio-file-'*25)}))
     return
    elif path=='/api/cookies':body={'cookies':[{'platform':'bilibili','has_cookie':True},{'platform':'youtube','has_cookie':True}]}
    elif path=='/api/settings/models':body={'models':['fixture-model', 'provider/'+('long-model-name-'*8)]+['model-'+str(i) for i in range(12)]}
    elif path=='/api/cookies/douyin/diagnose':body={'has_cookie':False,'looks_usable':False,'message':'No saved cookies','present':[],'missing':[],'cookie_count':0,'domains':[]}
    elif path=='/api/stats':body={k:12 for k in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_channels','total_videos','completed_videos']}
    elif path=='/api/summaries/bench':body=summary
    elif path=='/api/video-notes/tasks/bench':body=task
    elif path=='/api/video-notes/tasks/screenshots':body={**task,'id':'screenshots','markdown':screenshot_markdown,'versions':[]}
    elif path in ['/api/video-notes/tasks/saved-failed','/api/video-notes/tasks/saved-cancelled','/api/video-notes/tasks/saved-processing']:
     state=path.rsplit('-',1)[1]
     status={'failed':'failed','cancelled':'cancelled','processing':'summarizing'}[state]
     body={**task,'id':'saved-'+state,'status':status,'markdown':'# Saved complete note\n\nOriginal explanation remains readable.','error':'Provider temporarily unavailable' if state=='failed' else '', 'message':'Provider temporarily unavailable' if state=='failed' else 'Processing','versions':[]}
    elif path=='/api/video-notes/tasks/social':body={**task,'id':'social','title':'Original public article','platform':'substack','style':'original','formats':['original'],'model':'','duration':0,'markdown':social_markdown,'url':'https://writer.substack.com/p/public','versions':[]}
    elif path=='/api/video-notes/generate-json':
     submitted=route.request.post_data_json
     social_state['submitted'].append(submitted)
     body={'task_id':'generated-social','message':'Processing started'}
    elif path=='/api/summaries/recent':body=[]
    elif path=='/api/podcasts':body=[{'pid':'origin-'+platform,'title':'Source '+platform,'platform':platform,'description':'','cover_url':'','episode_count':1,'summarized_count':0} for platform in ['apple','spotify','xiaoyuzhou','local']]
    elif path=='/api/jobs':body={'jobs':[{'job_id':'fixture-job','episode_title':'A long podcast title / 一期较长的播客标题','status':'failed','created_at':1700000000,'progress':0,'message':'Connection needs attention'}]}
    elif path=='/api/content-updates':body={'items':[]}
    elif path=='/api/video-notes/channels':body={'channels':[{'platform':platform,'channel':f'{platform}-{i}','total':total,'done':done,'channel_avatar':'','thumbnail':'','channel_url':'','last_updated':''} for platform,count,total,done in [('bilibili',12,17,2),('youtube',4,34,5),('local',1,2,2),('twitter',2,3,1),('substack',1,4,4)] for i in range(count)]}
    elif path=='/api/library':body={'items':[{'id':'social','kind':'video','title':'Original public article','source':'Synthetic writer','date':'2026-10-24','published_at':'2026-10-23','status':'completed','platform':'substack','duration':0}] if social_state['library'] else [],'next_cursor':None}
    elif path.startswith('/api/video-notes/'):body={'tasks':[]}
    await route.fulfill(content_type='application/json',body=json.dumps(body))
   await page.route('**/api/**',api)
   await page.route('**/data/screenshots/fixture-missing.jpg*',lambda route:route.fulfill(status=404,body='Missing fixture'))
   async def fixture_image(route):
    portrait='portrait' in route.request.url
    await route.fulfill(content_type='image/svg+xml',body=f'<svg xmlns="http://www.w3.org/2000/svg" width="{600 if portrait else 960}" height="{1200 if portrait else 540}"><rect width="100%" height="100%" fill="#334155"/><text x="20" y="40" fill="white">Synthetic chart</text></svg>')
   await page.route('https://images.example.test/**',fixture_image)
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
   # A cold episode page must show its list while source metadata is pending,
   # and two submissions must retain their individual button states.
   episode_state['metadata']=asyncio.Event()
   await page.goto(origin+'/podcasts/fixture-source/episodes',wait_until='domcontentloaded')
   first=page.locator('[data-episode-id="one"]');second=page.locator('[data-episode-id="two"]')
   await first.get_by_role('button',name='Process',exact=True).wait_for()
   assert await first.get_by_role('button',name='Process',exact=True).is_disabled()
   episode_state['metadata'].set()
   await page.get_by_role('heading',name='Synthetic source · 一个较长的播客名称',exact=True).wait_for()
   await inspect('episodes')
   episode_state['one']=asyncio.Event();episode_state['two']=asyncio.Event()
   await first.get_by_role('button',name='Process',exact=True).click()
   await second.get_by_role('button',name='Process',exact=True).click()
   assert await first.get_by_role('button',name='Process',exact=True).is_disabled()
   assert await second.get_by_role('button',name='Process',exact=True).is_disabled()
   assert await first.get_by_role('button',name='Delete episode',exact=True).is_disabled()
   await inspect('parallel-episode-submissions')
   episode_state['one'].set()
   await first.get_by_role('button',name='Process',exact=True).wait_for(state='hidden')
   assert await second.get_by_role('button',name='Process',exact=True).is_disabled()
   episode_state['two'].set()
   await second.get_by_role('button',name='Process',exact=True).wait_for(state='hidden')
   assert episode_state['submitted']==['apple://one','apple://two']
   await page.screenshot(path=str(args.output/f'episodes-{width}.png'))
   await page.goto(origin+'/podcasts/fixture-local/episodes',wait_until='networkidle')
   await page.get_by_role('button',name='Upload Audio',exact=True).wait_for()
   await inspect('local-audio-tools')
   for attempt in range(2):
    await page.get_by_label('Local audio file',exact=True).set_input_files({'name':'fixture.wav','mimeType':'audio/wav','buffer':b'RIFF synthetic audio'})
    await page.wait_for_function("document.querySelector('input[type=file]')?.disabled===false")
    assert await page.get_by_label('Local audio file',exact=True).input_value()==''
   assert episode_state['uploads']==2
   await page.get_by_text('Synthetic audio format rejected',exact=False).first.wait_for()
   await inspect('long-upload-error')
   await page.screenshot(path=str(args.output/f'notifications-{width}.png'),animations='disabled')
   for path in ['/','/library','/podcasts','/videos','/settings','/viewer/bench','/videos/bench','/videos/social']:
    await page.goto(origin+path,wait_until='networkidle')
    await inspect(path)
    if path=='/podcasts':
     await page.get_by_role('button',name='Spotify',exact=False).first.click()
     await page.get_by_text('Source spotify',exact=True).wait_for()
     assert not await page.get_by_text('Source apple',exact=True).count()
     await inspect('spotify-podcast-category')
     assert await page.locator('.podcast-source-actions button').evaluate_all('(buttons)=>buttons.every(button=>{const range=document.createRange();range.selectNodeContents(button);return [...range.getClientRects()].filter(r=>r.height>0).every(r=>r.height<=30) && button.clientHeight<=60})'),(width,'source action labels fragmented')
     await page.screenshot(path=str(args.output/f'spotify-category-{width}.png'))
     await page.get_by_role('button',name='Apple Podcasts',exact=False).first.click()
     await page.get_by_text('Source apple',exact=True).wait_for()
     assert not await page.get_by_text('Source spotify',exact=True).count()
     await inspect('apple-podcast-category')
    if path=='/':
     await page.get_by_role('button',name='Open processing tasks',exact=True).click()
     await page.get_by_role('dialog',name='Processing tasks',exact=True).wait_for()
     assert await page.get_by_role('dialog',name='Processing tasks',exact=True).locator('time').get_attribute('datetime')=='2023-11-14T22:13:20.000Z'
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
     assert await cards.count()==5
     for card in await cards.all():
      result=await card.evaluate("""el=>{const title=el.querySelector('h3'),row=el.children[0].getBoundingClientRect(),stats=el.children[1].getBoundingClientRect();return {singleLine:title.getBoundingClientRect().height<=parseFloat(getComputedStyle(title).lineHeight)+1,stacked:stats.top>=row.bottom-1,contained:el.scrollWidth<=el.clientWidth+1}}""")
      assert all(result.values()),(width,result)
     await page.screenshot(path=str(args.output/f'platforms-{width}.png'))
     await page.get_by_role('button',name='Add content',exact=True).click()
     await page.get_by_label('Video URL',exact=True).fill('https://writer.substack.com/p/public')
     await page.get_by_text('Public text is imported in its original language',exact=False).wait_for()
     await inspect('social-content-form')
     await page.get_by_role('button',name='Add content',exact=True).click()
    if path=='/settings':
     # Cached settings may render immediately while a stale background read is
     # still pending. Neither that read nor a save acknowledgement may erase edits.
     holds['read']=asyncio.Event()
     await page.reload(wait_until='domcontentloaded')
     await page.get_by_label('Summary model',exact=True).select_option('openai/gpt-oss-20b')
     holds['read'].set()
     await page.get_by_text('Refreshing settings…',exact=True).wait_for(state='hidden')
     assert await page.get_by_label('Summary model',exact=True).input_value()=='openai/gpt-oss-20b'
     holds['read']=None
     holds['save']=asyncio.Event()
     await page.get_by_role('button',name='Save Settings',exact=True).click()
     await page.get_by_label('Transcription model',exact=True).select_option('whisper-large-v3-turbo')
     await page.get_by_role('button',name='教程 Tutorial',exact=True).click()
     holds['save'].set()
     await page.get_by_role('button',name='Save Settings',exact=True).wait_for()
     assert await page.get_by_role('button',name='Save Settings',exact=True).is_enabled()
     assert await page.get_by_label('Transcription model',exact=True).input_value()=='whisper-large-v3-turbo'
     assert await page.get_by_role('button',name='教程 Tutorial',exact=True).get_attribute('aria-pressed')=='true'
     assert await page.get_by_text('Unsaved changes',exact=True).count()==1
     holds['save']=None
     await page.get_by_role('button',name='Save Settings',exact=True).click()
     await page.get_by_text('All changes saved',exact=True).wait_for()
     holds['test']=asyncio.Event()
     await page.get_by_label('Summary model',exact=True).select_option('openai/gpt-oss-120b')
     await page.get_by_role('button',name='Test and save summaries',exact=True).click()
     assert await page.get_by_role('button',name='Save Settings',exact=True).is_disabled()
     holds['test'].set()
     await page.get_by_text('Connected and saved. Podcast and video summaries are ready.',exact=True).wait_for()
     holds['test']=None
     await page.get_by_role('button',name='Tools & Data',exact=True).click()
     await page.get_by_role('button',name='Check for Truncated',exact=True).click()
     await page.get_by_text('Found 1 truncated transcripts:',exact=True).wait_for()
     page.once('dialog',lambda dialog:dialog.accept())
     await page.get_by_role('button',name='Delete 1 Truncated',exact=True).click()
     await page.get_by_text('Failed to confirm cleanup:',exact=False).wait_for()
     assert await page.get_by_role('button',name='Delete 1 Truncated',exact=True).is_disabled()
     await inspect('maintenance-failure')
     await page.get_by_role('button',name='General',exact=True).click()
     await page.get_by_role('button',name='Tools & Data',exact=True).click()
     assert await page.get_by_text('Failed to confirm cleanup:',exact=False).is_visible()
     maintenance['empty']=True
     await page.get_by_role('button',name='Check for Truncated',exact=True).click()
     await page.get_by_text('No truncated transcripts found.',exact=True).wait_for()
     await page.get_by_role('button',name='General',exact=True).click()
     await page.get_by_label('Summary provider',exact=True).select_option('custom')
     await page.get_by_label('Summary Base URL',exact=True).wait_for()
     assert await page.get_by_text('Groq generates summaries',exact=False).count()==0
     await page.get_by_label('Summary Base URL',exact=True).fill('https://models.example.test/v1')
     await page.get_by_label('Summary API key',exact=True).fill('synthetic-test-key')
     model_picker=page.get_by_role('combobox',name='Summary model',exact=True)
     await model_picker.locator('option[value="model:fixture-model"]').wait_for(state='attached')
     assert await model_picker.locator('option[value^="model:"]').count()==14
     await model_picker.select_option('model:provider/'+('long-model-name-'*8))
     assert await page.get_by_label('Summary custom model',exact=True).count()==0
     await model_picker.scroll_into_view_if_needed()
     await inspect('custom-models')
     await page.screenshot(path=str(args.output/f'custom-models-{width}.png'))
     await model_picker.select_option('manual')
     await page.get_by_label('Summary custom model',exact=True).fill('private/manual-model')
     await inspect('custom-model-manual')
     await model_picker.select_option('model:fixture-model')
     async with page.expect_request('**/api/settings/test-llm') as model_test:
      await page.get_by_role('button',name='Test summary',exact=True).click()
     assert (await model_test.value).post_data_json['llm_model']=='fixture-model'
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
    if path in ['/viewer/bench','/videos/bench']:
     await page.evaluate("localStorage.setItem('xyz_pref:bench:notion_api_key','synthetic-test-key')")
     await page.get_by_role('button',name='Export',exact=True).click()
     await page.get_by_role('button',name='Send to Notion',exact=True).click()
     dialog=page.get_by_role('dialog',name='Export to Notion',exact=True)
     await dialog.get_by_role('button',name='📄 Synthetic notebook 0 · 一个较长的笔记本名称',exact=True).click()
     holds['notion']=asyncio.Event()
     await dialog.get_by_role('button',name='Export',exact=True).click()
     await dialog.get_by_text('Exporting to Notion…',exact=False).wait_for()
     assert await dialog.get_by_label('Search Notion pages',exact=True).is_disabled()
     await inspect('notion-exporting')
     holds['notion'].set()
     await dialog.get_by_text('Exported "Synthetic saved note" to Notion',exact=False).wait_for()
     assert await dialog.get_by_label('Search Notion pages',exact=True).is_disabled()
     await dialog.get_by_role('button',name='Close Notion export',exact=True).first.click()
     assert notion['submitted']==1
     await page.get_by_role('button',name='Export',exact=True).click()
     await page.get_by_role('button',name='Send to Notion',exact=True).click()
     await dialog.get_by_role('button',name='📄 Synthetic notebook 0 · 一个较长的笔记本名称',exact=True).click()
     notion['failed']=True
     await dialog.get_by_role('button',name='Export',exact=True).click()
     await dialog.get_by_role('alert').wait_for()
     assert not await dialog.get_by_role('button',name='Export',exact=True).count()
     if width<768:await page.set_viewport_size({'width':width,'height':420})
     await inspect('notion-incomplete')
     rect=await dialog.locator('>div').bounding_box()
     assert rect['y']>=0 and rect['y']+rect['height']<=(420 if width<768 else 844)+1,(width,rect)
     await dialog.get_by_role('button',name='Close Notion export',exact=True).last.scroll_into_view_if_needed()
     await page.screenshot(path=str(args.output/f'notion-{width}.png'))
     await dialog.get_by_role('button',name='Close Notion export',exact=True).last.click()
     await page.set_viewport_size({'width':width,'height':844})
     holds['notion']=None
     notion.update(failed=False,submitted=0)
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
    if path=='/videos/social':
     await page.get_by_role('tab',name='Original text',exact=True).wait_for()
     assert not await page.get_by_role('tab',name='Transcript',exact=True).count()
     await page.get_by_role('heading',name='Table of Contents',exact=True).wait_for()
     await page.get_by_text('Full final original paragraph. 原文末段完整保留。',exact=True).wait_for()
     await inspect('original-social-reader')
     await page.get_by_role('button',name='Export',exact=True).click()
     async with page.expect_download() as pending_download:
      await page.get_by_role('button',name='Markdown',exact=True).click()
     download=await pending_download.value
     file=args.output/f'original-social-{width}.md'
     await download.save_as(file)
     assert file.read_text()==social_markdown
     await page.screenshot(path=str(args.output/f'social-{width}.png'))
   for state in ['failed','cancelled','processing']:
    await page.goto(origin+'/videos/saved-'+state,wait_until='networkidle')
    await page.locator('[data-rendering="formatted"]').wait_for()
    await page.get_by_role('heading',name='Saved complete note',exact=True).wait_for()
    assert await page.get_by_text('Original explanation remains readable.',exact=True).count()==1
    assert not await page.get_by_text('Processing failed',exact=True).count()
    assert not await page.get_by_role('button',name='Cancel',exact=True).count()
    await page.get_by_role('button',name='Export',exact=True).click()
    assert await page.get_by_role('button',name='PDF',exact=True).count()==1
    assert await page.get_by_role('button',name='Send to Notion',exact=True).count()==1
    await inspect('saved-'+state)
    await page.screenshot(path=str(args.output/f'saved-{state}-{width}.png'))
   await page.goto(origin+'/videos/screenshots',wait_until='networkidle')
   await page.locator('[data-rendering="formatted"]').wait_for()
   await page.get_by_role('button',name='Open screenshot recovery',exact=True).click()
   panel=page.get_by_role('region',name='Screenshot recovery',exact=True)
   await panel.get_by_role('button',name='Repair screenshots',exact=True).wait_for(state='visible')
   assert await panel.evaluate('(el)=>document.activeElement===el'),(width,'recovery did not receive focus')
   await inspect('missing-screenshot-recovery')
   await panel.get_by_role('button',name='Download with images',exact=True).click()
   await panel.get_by_role('alert').filter(has_text='did not return a ZIP backup').wait_for()
   await inspect('backup-invalid-response')
   assert maintenance['bundle_requests']==1
   async with page.expect_download() as archive_download:
    await panel.get_by_role('button',name='Download with images',exact=True).click()
   archive_file=args.output/f'note-with-images-{width}.zip'
   await (await archive_download.value).save_as(archive_file)
   assert archive_file.read_bytes()==archive_bytes
   with zipfile.ZipFile(archive_file) as downloaded:
    assert downloaded.testzip() is None
    assert downloaded.read('images/chart.bin')==bytes(range(256))
    assert downloaded.read('note.md').decode()=='# Synthetic archive\n\n原始文字完整保留。'
   assert not await panel.get_by_role('alert').count()
   await inspect('backup-download-complete')
   await panel.get_by_role('button',name='Close details',exact=True).click()
   await page.locator('button.reader-screenshot').first.click()
   gallery=page.get_by_role('dialog',name='Enlarged screenshot',exact=True)
   await gallery.locator('.gallery-viewport img').wait_for(state='visible')
   if width<768:await page.set_viewport_size({'width':width,'height':420})
   await inspect('long-gallery-caption')
   assert await gallery.locator('.gallery-caption').text_content()==long_caption
   assert await gallery.locator('.gallery-viewport').evaluate('(el)=>el.clientHeight>=100'),(width,'caption displaced image')
   await page.screenshot(path=str(args.output/f'gallery-long-caption-{width}.png'))
   await gallery.locator('.gallery-viewport img').dispatch_event('error')
   await gallery.get_by_role('alert').wait_for()
   await inspect('gallery-download-error')
   await gallery.get_by_role('button',name='Retry original',exact=True).click()
   await gallery.locator('.gallery-viewport img').wait_for(state='visible')
   await page.keyboard.press('ArrowRight')
   await gallery.get_by_role('img',name='Portrait chart',exact=True).wait_for(state='visible')
   assert await gallery.locator('.gallery-viewport').evaluate('(el)=>{const v=el.getBoundingClientRect(),i=el.querySelector("img").getBoundingClientRect();return i.height>0&&i.bottom<=v.bottom+1&&i.right<=v.right+1}'),(width,'fit image exceeds available canvas')
   await page.screenshot(path=str(args.output/f'gallery-{width}.png'))
   await gallery.get_by_role('button',name='Close enlarged screenshot',exact=True).click()
   await page.set_viewport_size({'width':width,'height':844})
   social_state['library']=True
   await page.goto(origin+'/library',wait_until='networkidle')
   await page.get_by_role('button',name='Refresh library',exact=True).click()
   await page.get_by_role('heading',name='Original public article',exact=True).wait_for()
   await page.get_by_text('Read post',exact=True).wait_for()
   await inspect('social-library')
   await page.goto(origin+'/',wait_until='networkidle')
   for url in ['https://x.com/writer/status/123','https://writer.substack.com/p/public']:
    field=page.get_by_label('Podcast episode or video URL',exact=True)
    await field.fill(url)
    await field.press('Enter')
    await page.wait_for_function("document.querySelector('[aria-label=\"Podcast episode or video URL\"]')?.value===''")
   assert [row['platform'] for row in social_state['submitted']]==['twitter','substack']
   assert not errors,errors
   print(json.dumps({'width':width,'engine':'webkit' if args.webkit else 'chromium','button_text_contained':True,'icons_centered':True,'settings_and_reader_menus':True,'navigation_closes_on_route_change':width<768,'errors':errors}),flush=True)
   await context.close()
  await browser.close()
 server.shutdown()
asyncio.run(main())
