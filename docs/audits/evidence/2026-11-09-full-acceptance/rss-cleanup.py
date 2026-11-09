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
  saved=json.load(open(R/'rss-result.json'));pid=saved['created_pid'];assert not saved['was_existing']
  data=c.request.get(origin+'/api/podcasts/'+pid,headers=h).json()
  p.goto(origin+'/podcasts');p.get_by_role('button',name=__import__('re').compile('Apple Podcasts')).first.click()
  button=p.get_by_role('button',name='Remove '+data['title'],exact=True);button.wait_for();p.once('dialog',lambda d:d.accept())
  with p.expect_response(lambda r:r.request.method=='DELETE' and pid in r.url) as deleted:button.click()
  assert deleted.value.status==200;out['created_subscription_cleaned']=True;p.reload()
  verify=c.request.get(origin+'/api/podcasts/'+pid,headers=h);assert verify.status==404;out['refresh_api_absent']=True;out['status']='PASS'
  b.close()
except Exception as e:
 out['status']='FAIL';out['error_type']=type(e).__name__;out['error_line']=[f.lineno for f in __import__('traceback').extract_tb(e.__traceback__) if f.filename==__file__][-1]
(R/'rss-cleanup-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
