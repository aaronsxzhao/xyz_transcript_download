import os,json,getpass,time,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');out={'states':[]};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
def save():(R/'video-result.json').write_text(json.dumps(out,indent=2))
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False)
  def guard(route):
   r=route.request;p=urlsplit(r.url).path
   if r.method in ['GET','HEAD','OPTIONS'] or p=='/api/auth/signin' or p.startswith('/api/video-notes/upload') or p=='/api/video-notes/generate-json':return route.continue_()
   if p=='/api/performance':return route.fulfill(status=204)
   route.abort()
  c.route('**/*',guard);p=c.new_page();p.set_default_timeout(30000);p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;headers={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login');p.goto(origin+'/videos');p.get_by_role('button',name='Add content',exact=True).click()
  p.locator('input[type=file]').set_input_files(str(R/'AUDIT-20261109-SOFTWARE-VIDEO.mp4'))
  generate=p.get_by_role('button',name='Generate Notes',exact=True);expect(generate).to_be_enabled(timeout=90000)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/video-notes/generate-json') as creation:generate.click()
  assert creation.value.status==200;task=creation.value.json()['task_id'];out['task_id']=task;out['created_via_browser']=True;save();start=time.monotonic()
  while time.monotonic()-start<900:
   r=c.request.get(origin+'/api/video-notes/tasks/'+task,headers=headers);assert r.status==200;d=r.json();out['states'].append({'state':d.get('status'),'progress':d.get('progress'),'elapsed':round(time.monotonic()-start,2)});save()
   if d.get('status') in ['success','failed','cancelled']:break
   p.wait_for_timeout(5000)
  out['terminal']=d.get('status');out['error']=d.get('error');out['markdown_nonempty']=bool(d.get('markdown'));save()
  if d.get('status')=='success':
   p.goto(origin+'/videos/'+task);article=p.locator('#video-content-scroll article[data-rendering=formatted]');expect(article).to_be_visible(timeout=60000);p.wait_for_timeout(1500);before=article.inner_text();p.reload();expect(article).to_be_visible(timeout=60000);p.wait_for_timeout(1500);assert before==article.inner_text();out['rendered_refresh_equal']=True
   with p.expect_response(lambda r:urlsplit(r.url).path.endswith('/transcript')) as tr:p.get_by_role('tab',name='Transcript',exact=True).click()
   assert tr.value.status==200;out['transcript_http']=200;p.get_by_role('tab',name='Summary',exact=True).click()
  for w,h in [(1440,900),(768,1024),(390,844)]:p.set_viewport_size({'width':w,'height':h});p.screenshot(path=str(R/f'video-{w}.png'))
  out['status']='PASS' if d.get('status')=='success' else 'PIPELINE_FAIL';save();b.close()
except Exception as e:
 out['status']='FAIL';out['error_type']=type(e).__name__;out['error_line']=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1];save()
print(json.dumps(out))
