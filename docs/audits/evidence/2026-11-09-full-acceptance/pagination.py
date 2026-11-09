import os,json,getpass,time,io,wave
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');out={'created':[]};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
def save():(R/'pagination-result.json').write_text(json.dumps(out,indent=2))
buf=io.BytesIO()
with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*8000)
audio=buf.getvalue()
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.set_default_timeout(30000)
  p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
  for i in range(52):
   r=c.request.post(origin+'/api/podcasts/upload-audio',headers=h,multipart={'file':{'name':f'AUDIT-PAGE-{i:03}.wav','mimeType':'audio/wav','buffer':audio},'title':f'AUDIT-20261109-PAGE-{i:03}'},timeout=30000);assert r.status==200;out['created'].append(r.json()['episode']['eid']);save();p.wait_for_timeout(500)
  p.goto(origin+'/podcasts/local_uploads/episodes');rows=p.locator('[data-episode-id]');expect(rows.first).to_be_visible();p.wait_for_timeout(1000);out['initial_rows']=rows.count();assert out['initial_rows']<52
  t=time.monotonic();p.get_by_role('button',name='Load more episodes',exact=True).click();expect(rows).to_have_count(52);out['pagination_seconds']=round(time.monotonic()-t,3);out['all_ids_unique']=len(set(rows.evaluate_all('els=>els.map(e=>e.dataset.episodeId)')))==52;assert out['all_ids_unique'];save()
  chosen=out['created'][0]
  r=c.request.post(origin+'/api/process',headers=h,data={'episode_url':'local://'+chosen});assert r.status==200;job=r.json()['job_id'];out['cancel_job']=job;save()
  r=c.request.post(origin+'/api/jobs/'+job+'/cancel',headers=h);assert r.status==200
  for _ in range(30):
   state=c.request.get(origin+'/api/jobs/'+job,headers=h).json()['status']
   if state=='cancelled':break
   p.wait_for_timeout(1000)
  assert state=='cancelled';out['cancel_passed']=True
  r=c.request.post(origin+'/api/jobs/'+job+'/retry',headers=h);assert r.status==200;again=r.json()['new_job_id'];out['retry_job']=again;save();assert again!=job
  r=c.request.post(origin+'/api/jobs/'+again+'/cancel',headers=h);assert r.status==200
  for _ in range(30):
   state=c.request.get(origin+'/api/jobs/'+again,headers=h).json()['status']
   if state=='cancelled':break
   p.wait_for_timeout(1000)
  assert state=='cancelled';out['retry_new_attempt_then_cancel_passed']=True
  p.reload();expect(rows).to_have_count(out['initial_rows']);p.get_by_role('button',name='Load more episodes',exact=True).click();expect(rows).to_have_count(52);out['refresh_pagination_consistent']=True
  p.screenshot(path=str(R/'production-pagination.png'))
  out['cleanup_count']=0
  for eid in out['created']:
   r=c.request.delete(origin+'/api/episodes/'+eid,headers=h);assert r.status==200;out['cleanup_count']+=1;save()
  p.reload();expect(rows).to_have_count(0);out['cleaned_refresh_absent']=True;out['status']='PASS';save();b.close()
except Exception as e:
 out['status']='FAIL';out['error_type']=type(e).__name__;out['error_line']=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1];save()
print(json.dumps({k:v for k,v in out.items() if k!='created'}))
