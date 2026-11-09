import os,json,getpass,time,sys,re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
ROOT=Path('/workspace/acceptance-nov09-private');out={'created':[],'timings':[],'states':[]};email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ');origin='https://aipodcastsummary.online';prefix='AUDIT-20261109-SOFTWARE'
def save(): (ROOT/'software-result.json').write_text(json.dumps(out,indent=2))
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']})
  c=b.new_context(ignore_https_errors=False);allowed=set();jobid=None
  def guard(route):
   r=route.request;path=urlsplit(r.url).path
   if r.method in ['GET','HEAD','OPTIONS']:return route.continue_()
   if path=='/api/performance':return route.fulfill(status=204)
   if path in ['/api/auth/signin','/api/podcasts/upload-audio']:return route.continue_()
   if path=='/api/process' and r.method=='POST':
    d=r.post_data_json
    if d.get('episode_url','').removeprefix('local://') in allowed:return route.continue_()
   if r.method=='DELETE' and path.rsplit('/',1)[-1] in allowed:return route.continue_()
   return route.abort()
  c.route('**/*',guard);p=c.new_page();p.set_default_timeout(30000)
  p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;token=login.value.json()['access_token'];headers={'Authorization':'Bearer '+token};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
  settings=c.request.get(origin+'/api/settings',headers=headers).json();out['transcription_settings']={k:settings.get(k) for k in ['whisper_mode','whisper_provider','transcription_provider','whisper_key_saved']}
  for label in ['MAIN','DISPOSABLE']:
   p.goto(origin+'/podcasts');p.get_by_role('button',name='Upload Audio',exact=True).click();p.get_by_label('Audio file',exact=True).set_input_files(str(ROOT/'audit-software.wav'));p.get_by_label('Episode title',exact=True).fill(prefix+'-'+label)
   start=time.monotonic()
   with p.expect_response(lambda r:'/upload-audio' in r.url and r.request.method=='POST',timeout=90000) as uploaded:p.get_by_role('button',name='Upload',exact=True).click()
   assert uploaded.value.status==200;data=uploaded.value.json();eid=data['episode']['eid'];allowed.add(eid);out['created'].append({'eid':eid,'title':prefix+'-'+label,'pid':data['podcast']['pid']});out['timings'].append({'operation':'upload-'+label,'seconds':round(time.monotonic()-start,3)});save()
   p.wait_for_url('**/episodes');expect(p.locator(f'[data-episode-id="{eid}"]')).to_be_visible()
  main=out['created'][0]['eid'];discard=out['created'][1]['eid'];episodes=p.url
  p.reload();expect(p.locator(f'[data-episode-id="{main}"]')).to_be_visible();expect(p.locator(f'[data-episode-id="{discard}"]')).to_be_visible();out['upload_reload_passed']=True
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/process',timeout=30000) as processing:p.locator(f'[data-episode-id="{main}"]').get_by_role('button',name='Process',exact=True).click()
  assert processing.value.status==200;jobid=processing.value.json()['job_id'];out['job_id']=jobid;save()
  def status():
   r=c.request.get(origin+'/api/jobs/'+jobid,headers=headers);assert r.status==200;d=r.json();out['states'].append({'status':d.get('status'),'progress':d.get('progress'),'elapsed':round(time.monotonic()-begin,2)});save();return d
  begin=time.monotonic();current=status()
  deadline=time.monotonic()+90
  while current.get('status') not in ['summarizing','failed','completed'] and time.monotonic()<deadline:
   p.wait_for_timeout(1000);current=status()
  out['state_before_parallel_ui']=current.get('status');save()
  p.goto(origin+'/library');search=p.get_by_role('textbox',name='Search saved notes');search.wait_for();t=time.monotonic();search.fill('AUDIT-NO-MATCH-20261109');expect(p.get_by_text('No matching notes',exact=True)).to_be_visible();search.fill('');out['timings'].append({'operation':'search-clear-during-processing','seconds':round(time.monotonic()-t,3),'job_state':status().get('status')})
  t=time.monotonic();p.locator('a.library-card[data-kind="video"]').first.click();expect(p.locator('#video-content-scroll article[data-rendering=formatted]')).to_be_visible(timeout=60000);out['timings'].append({'operation':'read-existing-during-processing','seconds':round(time.monotonic()-t,3),'job_state':status().get('status')})
  p.goto(episodes);row=p.locator(f'[data-episode-id="{discard}"]');row.wait_for();row.get_by_label('More actions for '+prefix+'-DISPOSABLE').click();p.once('dialog',lambda d:d.accept());t=time.monotonic()
  with p.expect_response(lambda r:r.request.method=='DELETE' and discard in r.url) as deleted:row.get_by_role('button',name='Delete episode',exact=True).click()
  assert deleted.value.status==200;expect(row).to_have_count(0);out['disposable_deleted']=True;out['timings'].append({'operation':'delete-own-disposable','seconds':round(time.monotonic()-t,3),'job_state':status().get('status')});save()
  while time.monotonic()-begin<900:
   current=status()
   if current.get('status') in ['completed','failed','cancelled']:break
   p.wait_for_timeout(5000)
  out['terminal_status']=current.get('status');out['job_message']=str(current.get('message',''))[:350];out['job_error']=str(current.get('error',''))[:350]
  p.reload();expect(p.locator(f'[data-episode-id="{discard}"]')).to_have_count(0)
  if current.get('status')=='completed':
   row=p.locator(f'[data-episode-id="{main}"]');row.click();p.wait_for_url('**/viewer/'+main);out['reader_opened']=True
   r=c.request.get(origin+'/api/summaries/'+main,headers=headers);out['summary_http']=r.status;out['summary_nonempty']=bool(r.json().get('overview') or r.json().get('summary'))
  for w,h in [(1440,900),(768,1024),(390,844)]:
   p.set_viewport_size({'width':w,'height':h});p.screenshot(path=str(ROOT/f'software-{w}.png'))
  out['status']='PASS' if current.get('status')=='completed' else 'BLOCKED_PIPELINE';save();b.close()
except Exception as e:
 out['status']='HARNESS_OR_APP_FAILURE';out['error_type']=type(e).__name__;tb=__import__('traceback').extract_tb(e.__traceback__);out['error_line']=[x.lineno for x in tb if x.filename==__file__][-1];save()
print(json.dumps(out));sys.exit(0 if out.get('status')=='PASS' else 1)
