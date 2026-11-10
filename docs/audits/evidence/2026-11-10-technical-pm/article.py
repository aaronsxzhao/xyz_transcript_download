import os,json,getpass,time,hashlib,re,traceback
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from playwright.sync_api import sync_playwright,expect
R=Path(os.environ.get('AUDIT_OUTPUT','/tmp/aipodcast-audit-20261110'));R.mkdir(exist_ok=True);O='https://aipodcastsummary.online';E='de4246248271cec5cc24b32c';V='ae03fe78-a58';out={'checks':{},'http_errors':[],'console_errors':0,'page_errors':0,'timings':{},'screenshots':[]}
def save():(R/'result.json').write_text(json.dumps(out,indent=2))
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
created=[];test_url='https://example.com/?audit=technical-pm-20261110-'+str(int(time.time()))
email=getpass.getpass('Email (hidden): ');password=getpass.getpass('Password (hidden): ')
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False,accept_downloads=True);p=c.new_page();p.set_default_timeout(30000)
 def guard(route):
  path=urlsplit(route.request.url).path
  if path in ['/api/performance','/cdn-cgi/rum']:return route.fulfill(status=204)
  if route.request.method in ['GET','HEAD','OPTIONS'] or path in ['/api/auth/signin','/api/auth/refresh']:return route.continue_()
  if route.request.method=='POST' and path in ['/api/video-notes/generate','/api/video-notes/generate-json'] and test_url in (route.request.post_data or ''):return route.continue_()
  if route.request.method=='DELETE' and any(path=='/api/video-notes/tasks/'+ident for ident in created):return route.continue_()
  out.setdefault('blocked_methods_paths',[]).append({'method':route.request.method,'path':path});route.abort()
 c.route('**/*',guard)
 def response(r):
  if r.status>=400:out['http_errors'].append({'status':r.status,'kind':'api' if urlsplit(r.url).path.startswith('/api/') else r.request.resource_type})
 def console(m):
  if m.type=='error':
   out['console_errors']+=1;category=next((k for k in ['Content Security Policy','ERR_FAILED','WebSocket','ERR_BLOCKED'] if k in m.text),'other');out.setdefault('console_categories',{}).setdefault(category,0);out['console_categories'][category]+=1
 p.on('response',response);p.on('console',console);p.on('pageerror',lambda _:out.update(page_errors=out['page_errors']+1))
 try:
  health=c.request.get(O+'/api/health').json();assert health['revision']=='83307d55752d06fb1a917c6f5b98204a8abb603e' and health['status']=='ok';out['revision']=health['revision']
  p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login');out['checks']['login']=True
  # A new original-only public example; no media and no model processing.
  prior=c.request.get(O+'/api/video-notes/submission?'+urlencode({'url':test_url,'platform':'web'}),headers=h);assert prior.status==200 and not prior.json().get('task_id') and not prior.json().get('task')
  p.goto(O+'/videos');p.set_viewport_size({'width':1440,'height':900});p.get_by_role('button',name='Add content',exact=True).click();p.get_by_placeholder('Paste video, article, X or Substack link…').fill(test_url)
  t=time.monotonic()
  with p.expect_response(lambda r:urlsplit(r.url).path in ['/api/video-notes/generate','/api/video-notes/generate-json'] and r.request.method=='POST') as submitted:p.get_by_role('button',name='Import content',exact=True).click()
  assert submitted.value.status==200;ident=submitted.value.json()['task_id'];created.append(ident);out['created_test_ids']=list(created);save()
  for _ in range(60):
   response=c.request.get(O+'/api/video-notes/tasks/'+ident,headers=h);assert response.status==200;task=response.json()
   if task.get('status') in ['success','failed','cancelled']:break
   p.wait_for_timeout(1000)
  assert task['status']=='success' and task['style']=='original' and not task.get('model') and task['url']==test_url
  out['checks']['article_import']={'id':ident,'seconds':round(time.monotonic()-t,3),'source_characters':len(task.get('markdown','')),'style':task['style'],'model_empty':not task.get('model')};save()
  p.goto(O+'/videos/'+ident);article=p.locator('article');expect(article).to_be_visible(timeout=30000);expect(article).to_contain_text('documentation examples');expect(article.locator('.article-link-card')).to_be_visible();text=article.inner_text();expect(p.get_by_role('heading',name='Example Domain',exact=True).first).to_be_visible()
  p.get_by_role('button',name='Export',exact=True).click()
  with p.expect_download() as downloaded:p.get_by_role('button',name='Markdown',exact=True).click()
  d=downloaded.value;md=Path(d.path()).read_text();assert 'Example Domain' in md and 'documentation examples' in md;d.delete();p.reload();expect(article).to_contain_text('documentation examples');expect(article.locator('.article-link-card')).to_be_visible();assert article.inner_text()==text
  out['checks']['article_read_export_refresh']=True
  p.screenshot(path=str(R/'synthetic-article.png'));save()
  p.goto(O+'/videos?'+urlencode({'platform':'web','channel':task.get('channel') or '__unknown__'}))
  source=p.locator('a[href="'+test_url+'"]');expect(source).to_be_visible();card=source.locator('xpath=ancestor::div[contains(@class,"cursor-pointer")]').first
  card.get_by_label('More actions for '+task['title'],exact=True).click();p.once('dialog',lambda dialog:dialog.accept())
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/video-notes/tasks/'+ident and r.request.method=='DELETE') as deleted:card.get_by_role('button',name='Delete video',exact=True).click()
  assert deleted.value.status==200;expect(source).to_have_count(0);p.reload();expect(p.locator('a[href="'+test_url+'"]')).to_have_count(0)
  assert c.request.get(O+'/api/video-notes/tasks/'+ident,headers=h).status==404
  out['checks']['article_source_delete_ui_refresh']=True;created.remove(ident);out['cleanup']='all current-run content deleted';out['status']='PASS';save()
 except Exception as e:
  out.update(status='FAIL',error_type=type(e).__name__,error_line=[f.lineno for f in traceback.extract_tb(e.__traceback__) if f.filename==__file__][-1]);save()
 finally:
  for ident in created:
   item=c.request.get(O+'/api/video-notes/tasks/'+ident,headers=h)
   if item.status==200 and item.json().get('url')==test_url:
    cleanup=c.request.delete(O+'/api/video-notes/tasks/'+ident,headers=h);out['cleanup']={'fallback_status':cleanup.status,'id':ident};save()
  b.close()
print(json.dumps(out))
