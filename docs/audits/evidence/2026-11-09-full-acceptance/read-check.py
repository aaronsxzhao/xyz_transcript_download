import os,json,getpass,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/acceptance-nov09-private');out={};origin='https://aipodcastsummary.online';email=getpass.getpass('Test email (hidden): ');password=getpass.getpass('Test password (hidden): ')
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.set_default_timeout(30000)
 p.goto(origin+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
 with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as login:p.get_by_role('button',name='Sign In',exact=True).click()
 assert login.value.status==200;h={'Authorization':'Bearer '+login.value.json()['access_token']};p.wait_for_url(lambda u:urlsplit(str(u)).path!='/login')
 health=c.request.get(origin+'/api/health').json();out['revision']=health.get('revision');out['health']=health.get('status')
 if os.environ.get('EXPECTED_REVISION'):assert out['revision']==os.environ['EXPECTED_REVISION']
 jid='5a4028a6-3967-4686-852e-5aa01deb911a';j=c.request.get(origin+'/api/jobs/'+jid,headers=h);out['rss_job_before']=j.json().get('status') if j.status==200 else 'missing'
 p.goto(origin+'/library');search=p.get_by_role('textbox',name='Search saved notes');search.wait_for();t=time.monotonic();search.fill('AUDIT-NO-MATCH-20261109');expect(p.get_by_text('No matching notes',exact=True)).to_be_visible();search.fill('');out['search_clear_seconds']=round(time.monotonic()-t,3)
 t=time.monotonic();p.goto(origin+'/videos/ae03fe78-a58');article=p.locator('#video-content-scroll article[data-rendering=formatted]');expect(article).to_be_visible(timeout=60000);p.wait_for_timeout(1000);before=article.inner_text();out['open_reader_seconds']=round(time.monotonic()-t,3);p.reload();expect(article).to_be_visible(timeout=60000);p.wait_for_timeout(1000);assert article.inner_text()==before;out['summary_reload_equal']=True
 with p.expect_response(lambda r:urlsplit(r.url).path.endswith('/transcript')) as tr:p.get_by_role('tab',name='Transcript',exact=True).click()
 assert tr.value.status==200;out['transcript_http']=200;p.get_by_role('tab',name='Summary',exact=True).click();p.wait_for_timeout(500)
 j=c.request.get(origin+'/api/jobs/'+jid,headers=h);out['rss_job_after']=j.json().get('status') if j.status==200 else 'missing'
 # Redact the signed-in account label before taking evidence, not after image capture.
 p.evaluate('(email)=>{for(const el of document.querySelectorAll("*")){if(el.children.length===0 && el.textContent.includes(email))el.textContent="TEST ACCOUNT"}}',email)
 for w,hg in [(1440,900),(768,1024),(390,844)]:
  p.set_viewport_size({'width':w,'height':hg});p.wait_for_timeout(400);p.screenshot(path=str(R/f'verified-{w}.png'))
 out['status']='PASS';(R/'read-check-result.json').write_text(json.dumps(out,indent=2));b.close()
print(json.dumps(out))
