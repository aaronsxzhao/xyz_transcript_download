import os,getpass,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from urllib.parse import urlsplit
R=Path('/workspace/deep-acceptance-private');email=getpass.getpass('Email: ');password=getpass.getpass('Password: ');O='https://aipodcastsummary.online';out={}
with sync_playwright() as w:
 b=w.chromium.launch(executable_path='/usr/bin/chromium',chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
 with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as lr:p.get_by_role('button',name='Sign In',exact=True).click()
 assert lr.value.status==200;h={'Authorization':'Bearer '+lr.value.json()['access_token']}
 p.goto(O+'/podcasts/apple_290783428/episodes');rows=p.locator('[data-episode-id]');expect(rows.first).to_be_visible();p.wait_for_load_state('networkidle');out['episodes_initial']=rows.count();more=p.get_by_role('button',name='Load more episodes',exact=True);out['pagination_available']=more.count()>0
 if more.count():
  with p.expect_response(lambda r:urlsplit(r.url).path=='/api/podcasts/content' and 'offset=50' in r.url) as page2:more.click()
  response=page2.value;assert response.status==200;items=response.json();out['second_page_count']=len(items);out['second_page_http']=response.status
  if items:expect(rows).to_have_count(out['episodes_initial']+len(items))
  else:expect(more).to_have_count(0)
  out['episodes_after_more']=rows.count();ids=rows.evaluate_all('(els)=>els.map(x=>x.dataset.episodeId)');out['no_duplicate_ids']=len(ids)==len(set(ids))
 p.goto(O+'/videos/ae03fe78-a58');article=p.locator('article[data-rendering=formatted]');expect(article).to_be_visible();p.wait_for_load_state('networkidle');before=article.inner_text();c.set_offline(True);out['already_loaded_reader_stays_readable']=article.inner_text()==before;c.set_offline(False);p.reload();expect(article).to_be_visible();p.wait_for_load_state('networkidle');out['reconnected_reload_equal']=before==article.inner_text()
 with c.expect_page() as tab:p.evaluate("url=>window.open(url,'_blank')",O+'/videos/ae03fe78-a58')
 q=tab.value;expect(q.locator('article[data-rendering=formatted]')).to_be_visible();q.wait_for_load_state('networkidle');out['second_tab_equal']=q.locator('article[data-rendering=formatted]').inner_text()==before;q.close();out['status']='PASS';(R/'additional-readonly.json').write_text(json.dumps(out,indent=2));print(json.dumps(out));b.close()
