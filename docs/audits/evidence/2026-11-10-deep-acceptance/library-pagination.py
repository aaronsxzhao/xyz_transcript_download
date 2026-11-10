import os,getpass,json,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from urllib.parse import urlsplit
R=Path('/workspace/deep-acceptance-private');email=getpass.getpass('Email: ');password=getpass.getpass('Password: ');O='https://aipodcastsummary.online';out={}
with sync_playwright() as w:
 b=w.chromium.launch(executable_path='/usr/bin/chromium',chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
 with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as lr:p.get_by_role('button',name='Sign In',exact=True).click()
 assert lr.value.status==200;h={'Authorization':'Bearer '+lr.value.json()['access_token']}
 made=[];prefix='https://example.com/?audit=deep-pagination-'+str(int(time.time()))+'-';out={'created':[],'cleaned':[]}
 def save():(R/'library-pagination.json').write_text(json.dumps(out,indent=2))
 try:
  for i in range(35):
   url=prefix+str(i);r=c.request.post(O+'/api/video-notes/generate-json',headers=h,data={'url':url,'platform':'web','style':'original','formats':['original'],'skip_existing':True});assert r.status==200;ident=r.json()['task_id'];made.append((ident,url));out['created'].append(ident);save()
   for attempt in range(90):
    item=c.request.get(O+'/api/video-notes/tasks/'+ident,headers=h).json()
    if item.get('status') in ['success','failed','cancelled']:break
    p.wait_for_timeout(1000)
   assert item['status']=='success' and item['style']=='original' and not item.get('model')
  p.goto(O+'/library');cards=p.locator('a.library-card,article.series-card');expect(cards.first).to_be_visible();p.wait_for_load_state('networkidle');out['initial_cards']=cards.count();more=p.get_by_role('button',name='Show more notes',exact=True);expect(more).to_be_visible();more.click();expect(cards).not_to_have_count(out['initial_cards']);p.wait_for_load_state('networkidle');out['after_more']=cards.count();out['new_source_cards']=p.locator('a.library-card').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))');out['new_source_cards']=sum(any(ident in href for ident,_ in made) for href in out['new_source_cards']);assert out['new_source_cards']==35
  search=p.get_by_role('textbox',name='Search saved notes');search.fill('Example Domain');p.wait_for_load_state('networkidle');out['search_count']=cards.count();search.clear();p.reload();expect(cards.first).to_be_visible();expect(p.get_by_role('button',name='Show more notes',exact=True)).to_be_visible();out['refresh_page_boundary']=True;out['status']='PASS';save()
 finally:
  for ident,url in made:
   r=c.request.get(O+'/api/video-notes/tasks/'+ident,headers=h)
   if r.status==200 and r.json().get('url')==url:
    deleted=c.request.delete(O+'/api/video-notes/tasks/'+ident,headers=h);assert deleted.status==200;out['cleaned'].append(ident);save()
  out['all_created_cleaned']=len(made)==len(out['cleaned']);save();b.close()
 print(json.dumps({k:v for k,v in out.items() if k not in ['created','cleaned']}))
