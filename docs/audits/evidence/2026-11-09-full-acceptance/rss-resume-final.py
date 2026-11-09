import os,json,getpass,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');out={'states':[]};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
def save():(R/'rss-full-result.json').write_text(json.dumps(out,indent=2))
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.set_default_timeout(30000)
  p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
  out=json.loads((R/'rss-full-interrupted.json').read_text());out.pop('status',None);pid=out['created_pid'];eid=out['episode_id'];jid=out['job_id'];start=time.monotonic();out['resumed_read_only']=True
  while time.monotonic()-start<900:
   r=c.request.get(origin+'/api/jobs/'+jid,headers=h);out.setdefault('poll_http',[]).append(r.status);save();assert r.status==200;d=r.json();out['states'].append({'status':d.get('status'),'elapsed':round(time.monotonic()-start,2)});save()
   if d.get('status') in ['completed','failed','cancelled']:break
   p.wait_for_timeout(5000)
  out['terminal']=d.get('status');out['error_code']=d.get('error_code');out['has_error']=bool(d.get('error'));save()
  if d.get('status')=='completed':
   p.goto(origin+'/viewer/'+eid);panel=p.locator('#podcast-summary');expect(panel).to_be_visible(timeout=60000);p.wait_for_timeout(1500);before=panel.inner_text();assert len(before)>100;out['rendered_summary_present']=True;s=c.request.get(origin+'/api/summaries/'+eid,headers=h);assert s.status==200;out['summary_nonempty']=bool(s.json().get('overview') or s.json().get('summary'));p.reload();p.wait_for_timeout(1500);s2=c.request.get(origin+'/api/summaries/'+eid,headers=h);out['summary_refresh_equal']=s.json()==s2.json();out['reader_url_correct']=urlsplit(p.url).path=='/viewer/'+eid;expect(panel).to_be_visible();assert panel.inner_text()==before;out['rendered_reload_equal']=True
   with p.expect_response(lambda r:urlsplit(r.url).path=='/api/transcripts/'+eid) as tr:p.get_by_role('tab',name='Transcript',exact=True).click()
   assert tr.value.status==200 and tr.value.json().get('segments');out['transcript_read']=True
  # Cleanup only subscription this run created; do not touch any other source.
  deleted=c.request.delete(origin+'/api/podcasts/'+pid,headers=h);out['cleanup_http']=deleted.status;p.goto(origin+'/podcasts');p.reload();out['cleaned']=c.request.get(origin+'/api/podcasts/'+pid,headers=h).status==404
  out['status']='PASS' if d.get('status')=='completed' and out.get('summary_nonempty') and out.get('summary_refresh_equal') and out.get('cleaned') else 'BLOCKED';save();b.close()
except Exception as e:
 out.update(status='FAIL',error_type=type(e).__name__,error_line=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1]);save()
print(json.dumps(out))
