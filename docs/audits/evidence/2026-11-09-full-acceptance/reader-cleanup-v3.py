import os,json,getpass,hashlib,sys,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');created=json.load(open(R/'software-result.json'));eid=created['created'][0]['eid'];garden=json.load(open(R/'podcast-result.json'))['created'][0]['eid'];allowed={eid,garden};out={};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False)
  def guard(route):
   r=route.request;p=urlsplit(r.url).path
   if r.method in ['GET','HEAD','OPTIONS'] or p=='/api/auth/signin' or r.method=='DELETE' and p.rsplit('/',1)[-1] in allowed:return route.continue_()
   if p=='/api/performance':return route.fulfill(status=204)
   route.abort()
  c.route('**/*',guard);p=c.new_page();p.set_default_timeout(30000);p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;token=login.value.json()['access_token'];headers={'Authorization':'Bearer '+token};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
  def get(path):return c.request.get(origin+path,headers=headers)
  p.goto(origin+'/viewer/'+eid);panel=p.locator('#podcast-summary');expect(panel).to_be_visible();p.wait_for_timeout(1500);before=panel.inner_text();assert len(before)>100
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/transcripts/'+eid) as transcript:p.get_by_role('tab',name='Transcript',exact=True).click()
  assert transcript.value.status==200;assert transcript.value.json().get('segments');out['transcript_read']=True
  p.get_by_role('tab',name='Summary',exact=True).click();p.reload();expect(panel).to_be_visible();assert panel.inner_text()==before;out['summary_reload_equal']=True
  
  with c.expect_page() as newtab:p.evaluate("url=>window.open(url,'_blank')",origin+'/viewer/'+eid)
  q=newtab.value;q.wait_for_load_state();expect(q.locator('#podcast-summary')).to_be_visible();q.wait_for_timeout(1500);out['tab_comparison']={'first_chars':len(before),'second_chars':len(q.locator('#podcast-summary').inner_text())};assert q.locator('#podcast-summary').inner_text()==before;out['second_tab_equal']=True
  c.set_offline(True)
  try:p.reload(timeout=10000)
  except Exception:out['offline_reload_failed_expected']=True
  c.set_offline(False);p.goto(origin+'/viewer/'+eid);expect(panel).to_be_visible();assert panel.inner_text()==before;out['online_recovery_equal']=True
  p.goto(origin+'/podcasts/local_uploads/episodes');row=p.locator(f'[data-episode-id="{eid}"]');row.get_by_label('More actions for '+created['created'][0]['title']).click();p.once('dialog',lambda d:d.accept())
  with p.expect_response(lambda r:r.request.method=='DELETE' and '/api/summaries/'+eid in r.url) as deletion:row.get_by_role('button',name='Delete summary only',exact=True).click()
  assert deletion.value.status==200;assert get('/api/summaries/'+eid).status==404;assert get('/api/transcripts/'+eid).status==200;assert get('/api/episodes/'+eid).status==200;out['summary_only_preserves_transcript_and_source']=True
  q.reload();expect(q.locator('#podcast-summary')).to_have_count(0);out['second_tab_reload_no_stale_summary']=True
  p.reload();row=p.locator(f'[data-episode-id="{eid}"]');row.get_by_label('More actions for '+created['created'][0]['title']).click();p.once('dialog',lambda d:d.accept())
  with p.expect_response(lambda r:r.request.method=='DELETE' and '/api/episodes/'+eid in r.url) as deletion:row.get_by_role('button',name='Delete episode',exact=True).click()
  assert deletion.value.status==200;p.reload();expect(p.locator(f'[data-episode-id="{eid}"]')).to_have_count(0);assert get('/api/episodes/'+eid).status==404;assert get('/api/transcripts/'+eid).status==404;out['source_delete_refresh_absent']=True
  # Clean only the other main source created by this run;never touch existing uploads.
  row=p.locator(f'[data-episode-id="{garden}"]');row.get_by_label('More actions for AUDIT-20261109-GARDEN-MAIN').click();p.once('dialog',lambda d:d.accept())
  with p.expect_response(lambda r:r.request.method=='DELETE' and garden in r.url) as deletion:row.get_by_role('button',name='Delete episode',exact=True).click()
  assert deletion.value.status==200;out['garden_source_cleaned']=True
  for w,h in [(1440,900),(768,1024),(390,844)]:p.set_viewport_size({'width':w,'height':h});p.screenshot(path=str(R/f'cleaned-{w}.png'))
  out['status']='PASS';b.close()
except Exception as e:
 out['status']='FAIL';out['error_type']=type(e).__name__;out['error_line']=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1]
(R/'cleanup-v3-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
