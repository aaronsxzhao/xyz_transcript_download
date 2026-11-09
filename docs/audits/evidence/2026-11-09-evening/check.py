import os,json,getpass,time,hashlib,re,traceback
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/evening-validation/followup');R.mkdir(exist_ok=True);O='https://aipodcastsummary.online';E='de4246248271cec5cc24b32c';V='ae03fe78-a58';out={'checks':{},'http_errors':[],'console_errors':0,'page_errors':0,'timings':{},'screenshots':[]}
def save():(R/'result.json').write_text(json.dumps(out,indent=2))
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
email=getpass.getpass('Email (hidden): ');password=getpass.getpass('Password (hidden): ')
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False,accept_downloads=True);p=c.new_page();p.set_default_timeout(30000)
 def guard(route):
  path=urlsplit(route.request.url).path
  if path=='/api/performance':return route.fulfill(status=204)
  if route.request.method in ['GET','HEAD','OPTIONS'] or path=='/api/auth/signin':return route.continue_()
  out.setdefault('blocked_methods_paths',[]).append({'method':route.request.method,'path':path});route.abort()
 c.route('**/*',guard)
 def response(r):
  if r.status>=400:out['http_errors'].append({'status':r.status,'kind':'api' if urlsplit(r.url).path.startswith('/api/') else r.request.resource_type})
 def console(m):
  if m.type=='error':
   out['console_errors']+=1;category=next((k for k in ['Content Security Policy','ERR_FAILED','WebSocket','ERR_BLOCKED'] if k in m.text),'other');out.setdefault('console_categories',{}).setdefault(category,0);out['console_categories'][category]+=1
 p.on('response',response);p.on('console',console);p.on('pageerror',lambda _:out.update(page_errors=out['page_errors']+1))
 try:
  health=c.request.get(O+'/api/health').json();assert health['revision']=='8a660a41baa5cb21c4783fd3f90451b040e4f0d4' and health['status']=='ok';out['revision']=health['revision']
  p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login');out['checks']['login']=True
  p.goto(O+'/library');cards=p.locator('a.library-card,article.series-card');expect(cards.first).to_be_visible();p.wait_for_load_state('networkidle');count=cards.count();assert count>=2;search=p.get_by_role('textbox',name='Search saved notes');t=time.monotonic();search.fill('AUDIT-NOV09-EVENING-NO-MATCH');expect(p.get_by_text('No matching notes',exact=True)).to_be_visible();search.press('Control+A');search.press('Backspace');expect(cards).to_have_count(count);out['timings']['search_clear_seconds']=round(time.monotonic()-t,3);out['checks']['library']={'count':count,'search_clear':True,'pagination_control':p.get_by_role('button',name='Show more notes').count()>0};save()
  series=p.locator('article.series-card').first
  with p.expect_response(lambda r:'/collections/' in r.url and urlsplit(r.url).path.endswith('/parts')) as parts:series.get_by_role('button',name='View episodes').click()
  assert parts.value.status==200;data=parts.value.json()['parts'];out['checks']['multipart']={'parts':len(data),'pages':[v['page'] for v in data],'ready_count':sum(v.get('status')=='success' for v in data)};assert len(data)==2;expect(series.locator('.series-episodes li')).to_have_count(2);save()
  p.goto(O+'/videos/'+V);article=p.locator('#video-content-scroll article[data-rendering=formatted]');expect(article).to_be_visible(timeout=60000);p.wait_for_load_state('networkidle');before=article.inner_text();assert len(before)>100
  with p.expect_response(lambda r:urlsplit(r.url).path.endswith('/transcript')) as tr:p.get_by_role('tab',name='Transcript',exact=True).click()
  assert tr.value.status==200;expect(p.locator('#video-transcript')).not_to_be_empty();p.get_by_role('tab',name='Summary',exact=True).click();p.get_by_role('button',name='More summary actions',exact=True).click();p.get_by_role('button',name='Version history',exact=True).click();versions=p.get_by_role('combobox',name='Note version');expect(versions).to_be_visible();expect(versions.locator('option').first).to_be_attached();version_count=versions.locator('option').count();out['checks']['video_versions']={'options':version_count}
  if version_count>1:
   with p.expect_response(lambda r:'/versions/' in urlsplit(r.url).path) as old:versions.select_option(index=1)
   assert old.value.status==200 and old.value.json().get('content');expect(article).to_be_visible();versions.select_option(index=0);p.wait_for_load_state('networkidle');assert article.inner_text()==before;out['checks']['video_versions']['restore_equal']=True
  p.reload();expect(article).to_be_visible();p.wait_for_load_state('networkidle');assert article.inner_text()==before;out['checks']['video_reload']=True;save()
  p.goto(O+'/viewer/'+E);panel=p.locator('#podcast-summary');expect(panel).to_be_visible(timeout=60000);p.wait_for_load_state('networkidle');original=panel.inner_text();assert len(original)>100;summary=c.request.get(O+'/api/summaries/'+E,headers=h);assert summary.status==200;source=summary.json()
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/transcripts/'+E) as tr:p.get_by_role('tab',name='Transcript',exact=True).click()
  assert tr.value.status==200 and tr.value.json().get('segments');out['checks']['rss_transcript_segments']=len(tr.value.json()['segments']);p.get_by_role('tab',name='Summary',exact=True).click()
  p.get_by_role('button',name='Export',exact=True).click();t=time.monotonic()
  with p.expect_download() as dl:p.get_by_role('button',name='Markdown',exact=True).click()
  download=dl.value;blob=Path(download.path()).read_text();assert download.suggested_filename.endswith('.md') and source['title'] in blob and len(blob)>len(original)//2;out['checks']['markdown_export']={'bytes':len(blob.encode()),'sha256':digest(blob),'title_present':True,'key_points':len(source.get('key_points',[]))};out['timings']['markdown_download_seconds']=round(time.monotonic()-t,3);download.delete();save()
  p.get_by_role('button',name='Export',exact=True).click();t=time.monotonic()
  with c.expect_page() as popup:p.get_by_role('link',name='Open as HTML',exact=True).click()
  q=popup.value;q.wait_for_load_state('domcontentloaded');htmlbody=q.locator('body').inner_text();assert source['title'] in htmlbody and len(htmlbody)>len(original)//2;out['checks']['html_export']={'text_length':len(htmlbody),'title_present':True,'scripts':q.locator('script').count()};out['timings']['html_open_seconds']=round(time.monotonic()-t,3);out['checks']['html_export']['script_sources']=q.locator('script').evaluate_all("els=>els.map(e=>({inline:!e.src,host:e.src?new URL(e.src).hostname:null}))");details=q.locator('details.quote');out['checks']['html_export']['quote_count']=details.count();assert details.count()==sum(bool(k.get('original_quote')) for k in source.get('key_points',[]));details.first.locator('summary').click();expect(details.first).to_have_attribute('open','');expect(details.first.locator('blockquote')).to_be_visible();out['checks']['html_export']['native_quote_expansion']=True;q.close();save()
  p.reload();expect(panel).to_be_visible();p.wait_for_load_state('networkidle');assert panel.inner_text()==original;out['checks']['rss_reload_equal']=True
  for w,height in [(1440,900),(768,1024),(390,844)]:
   p.set_viewport_size({'width':w,'height':height});p.wait_for_timeout(300);assert not p.evaluate('document.documentElement.scrollWidth>innerWidth');name=f'reader-{w}x{height}.png';p.screenshot(path=str(R/name));out['screenshots'].append(name)
  before_jobs=c.request.get(O+'/api/jobs',headers=h).json().get('jobs',[]);active=[v for v in before_jobs if v.get('status') in ['pending','fetching','downloading','transcribing','summarizing']];out['checks']['tasks']={'total':len(before_jobs),'active':len(active)}
  p.goto(O+'/');p.get_by_role('button',name=re.compile('Task history|Review tasks')).first.click();expect(p.get_by_role('dialog',name='Task history')).to_be_visible();p.reload();p.get_by_role('button',name=re.compile('Task history|Review tasks')).first.click();expect(p.get_by_role('dialog',name='Task history')).to_be_visible();after_jobs=c.request.get(O+'/api/jobs',headers=h).json().get('jobs',[])
  if not active:assert sorted((v['job_id'],v['status']) for v in before_jobs)==sorted((v['job_id'],v['status']) for v in after_jobs)
  out['checks']['tasks']['reload_consistent']=not active;out['status']='PASS';save()
 except Exception as e:
  out.update(status='FAIL',error_type=type(e).__name__,error_line=[f.lineno for f in traceback.extract_tb(e.__traceback__) if f.filename==__file__][-1]);save()
 finally:b.close()
print(json.dumps(out))
