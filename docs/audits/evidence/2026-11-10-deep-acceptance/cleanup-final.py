import os,getpass,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from urllib.parse import urlsplit
R=Path('/workspace/deep-acceptance-private');email=getpass.getpass('Email: ');password=getpass.getpass('Password: ');O='https://aipodcastsummary.online';out={}
with sync_playwright() as w:
 b=w.chromium.launch(executable_path='/usr/bin/chromium',chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
 with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as lr:p.get_by_role('button',name='Sign In',exact=True).click()
 assert lr.value.status==200;h={'Authorization':'Bearer '+lr.value.json()['access_token']}
 data=json.loads((R/'library-pagination.json').read_text());tasks=c.request.get(O+'/api/video-notes/tasks',headers=h).json()['tasks'];assert not set(data['created'])&{v['id'] for v in tasks};out['created_ids_absent']=True;out['remaining_video_tasks']=len(tasks)
 p.goto(O+'/library');cards=p.locator('a.library-card,article.series-card');expect(cards).to_have_count(7);p.reload();expect(cards).to_have_count(7);out['library_restored_cards']=7;out['reload_consistent']=True
 jobs=c.request.get(O+'/api/jobs',headers=h).json()['jobs'];out['active_jobs']=sum(j['status'] not in ['completed','failed','cancelled'] for j in jobs);health=c.request.get(O+'/api/health').json();out['health']={k:health.get(k) for k in ['revision','status']};out['status']='PASS';(R/'cleanup-final.json').write_text(json.dumps(out,indent=2));print(json.dumps(out));b.close()
