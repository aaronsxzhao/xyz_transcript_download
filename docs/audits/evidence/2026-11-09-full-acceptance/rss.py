import os,json,getpass,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');out={};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.set_default_timeout(30000)
  p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
  assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
  previous=c.request.get(origin+'/api/podcasts',headers=h).json();previous=previous.get('podcasts',[]) if isinstance(previous,dict) else previous;old={x['pid'] for x in previous}
  p.goto(origin+'/podcasts');p.get_by_role('button',name='Add Podcast',exact=True).click();p.get_by_label('Podcast URL',exact=True).fill('https://podcasts.apple.com/us/podcast/the-daily/id1200361736')
  t=time.monotonic()
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/podcasts' and r.request.method=='POST',timeout=90000) as added:p.get_by_role('button',name='Add',exact=True).click()
  out['import_http']=added.value.status;out['import_seconds']=round(time.monotonic()-t,3)
  if added.value.status!=200:
   out['error_category']='source_import_rejected';out['status']='BLOCKED'
  else:
   data=added.value.json();pid=data['pid'];out['created_pid']=pid;out['was_existing']=pid in old;(R/'rss-result.json').write_text(json.dumps(out))
   p.goto(origin+'/podcasts/'+pid+'/episodes');rows=p.locator('[data-episode-id]');expect(rows.first).to_be_visible(timeout=60000);out['visible_episode_count']=rows.count();p.reload();expect(rows.first).to_be_visible();out['refresh_episode_count']=rows.count();assert out['refresh_episode_count']==out['visible_episode_count'];out['source_import_read_refresh']=True
   p.screenshot(path=str(R/'rss-episodes.png'))
   if pid not in old:
    p.goto(origin+'/podcasts');button=p.get_by_role('button',name='Remove '+data['title'],exact=True);button.wait_for();p.once('dialog',lambda d:d.accept())
    with p.expect_response(lambda r:r.request.method=='DELETE' and pid in r.url) as deleted:button.click()
    assert deleted.value.status==200;out['created_subscription_cleaned']=True;p.reload();expect(button).to_have_count(0)
   out['status']='PASS'
  b.close()
except Exception as e:
 out['status']='FAIL';out['error_type']=type(e).__name__;out['error_line']=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1]
(R/'rss-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
