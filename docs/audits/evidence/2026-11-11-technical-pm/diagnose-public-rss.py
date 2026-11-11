# Prepared diagnosis. No production writes; model output and transcript stay in memory.
import os,sys,json,time,getpass,threading,logging,datetime
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
import requests
R=Path(os.environ['AUDIT_OUTPUT']);R.mkdir(parents=True,exist_ok=True);sys.path.insert(0,os.environ['AUDIT_REPO']);os.environ['XYZ_DATA_DIR']=str(R/'isolated-data');logging.disable(logging.CRITICAL)
keypath=Path(os.environ['AUDIT_KEY_FILE']);key=keypath.read_text().strip();keypath.unlink()
email=getpass.getpass('Email: ');password=getpass.getpass('Password: ');O='https://aipodcastsummary.online';out={'calls':0,'stages':[]};lock=threading.RLock();gate=threading.BoundedSemaphore(3);last_budget=[0]
def save():
 with lock:(R/'reproduce-bounded.json').write_text(json.dumps(out,indent=2))
def budget():
 z=datetime.timezone(datetime.timedelta(hours=8));day=datetime.datetime.now(z).date();r=requests.get('https://api.aipaibox.com/api/log/token',headers={'Authorization':'Bearer '+key},timeout=30);r.raise_for_status();rows=r.json()['data'];assert datetime.datetime.fromtimestamp(min(x['created_at'] for x in rows),z).date()<day
 out['daily_usd']=sum(x['quota'] for x in rows if x['type']==2 and datetime.datetime.fromtimestamp(x['created_at'],z).date()==day)/500000;assert out['daily_usd']<40;last_budget[0]=time.monotonic();save()
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']});c=b.new_context(ignore_https_errors=False);p=c.new_page();p.goto(O+'/login');p.get_by_label('Email',exact=True).fill(email);p.get_by_label('Password',exact=True).fill(password)
 with p.expect_response(lambda r:urlsplit(r.url).path=='/api/auth/signin') as lr:p.get_by_role('button',name='Sign In',exact=True).click()
 assert lr.value.status==200;h={'Authorization':'Bearer '+lr.value.json()['access_token']};jobs=c.request.get(O+'/api/jobs',headers=h).json()['jobs'];assert all(x['status'] in ['failed','completed','cancelled'] for x in jobs)
 ep=c.request.get(O+'/api/episodes/9826f3225eb2936514291994',headers=h).json();assert ep['pid']=='apple_290783428' and ep['duration']==1943
 pod=c.request.get(O+'/api/podcasts/apple_290783428',headers=h).json();assert urlsplit(pod['feed_url']).hostname=='feeds.npr.org'
 td=c.request.get(O+'/api/transcripts/9826f3225eb2936514291994',headers=h).json();settings=c.request.get(O+'/api/settings',headers=h).json();assert settings['llm_provider']=='custom';base=settings['llm_base_url'];assert urlsplit(base).hostname=='api.aipaibox.com';b.close()
budget()
from summarizer import Summarizer
from transcriber import Transcript,TranscriptSegment
from model_execution import request_options
from summary_errors import ProcessingCancelledError
engine=Summarizer(api_key=key,base_url=base,model=settings['llm_model'],custom_endpoint=True,model_options=request_options(settings,base,settings['llm_model']),generation_mode=settings.get('summary_generation_mode','single'))
from types import SimpleNamespace
active=[0];peak=[0]
class BoundedClient:
 def __init__(self,raw):
  self.raw=raw
  self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
 def __getattr__(self,name):return getattr(self.raw,name)
 def with_options(self,**kwargs):return BoundedClient(self.raw.with_options(**kwargs))
 def create(self,**kwargs):
  with gate:
   with lock:
    if out['calls']>=20:raise ProcessingCancelledError('Audit request limit reached')
    if time.monotonic()-last_budget[0]>60:budget()
    out['calls']+=1;active[0]+=1;peak[0]=max(peak[0],active[0]);save()
   try:return self.raw.chat.completions.create(**kwargs)
   finally:
    with lock:active[0]-=1
engine.client=BoundedClient(engine.client)

tr=Transcript(td['episode_id'],td['language'],td['duration'],td['text'],[TranscriptSegment(**{k:v[k] for k in ['start','end','text']}) for v in td['segments']]);out['segments']=len(tr.segments)
def stage(e):
 with lock:out['stages'].append({k:v for k,v in e.items() if k in ['stage','current','total']});save()
try:
 summary=engine.summarize(tr,episode_title=ep['title'],stage_callback=stage);out['result']='generated_in_memory_only';out['points']=len(summary.key_points) if summary else 0
except Exception as e:out.update(result='failed',error_type=type(e).__name__,code=getattr(e,'code',None),reason=getattr(e,'reason',None))
finally:
 report=engine.generation_report;out['wall_seconds']=report.get('wall_seconds');out['peak_concurrency']=peak[0]
 for category in ['coverage_ledger','verification','delivery']:out[category]={k:v for k,v in report.get(category,{}).items() if isinstance(v,(int,float,bool)) or k=='status'}
 items=report.get('coverage_ledger',{}).get('items',[]);out['item_statuses']={s:sum(x['status']==s for x in items) for s in set(x['status'] for x in items)};save();engine.client.close()
try:budget()
except Exception as e:out['final_budget_error']=type(e).__name__;save()
print(json.dumps({k:v for k,v in out.items() if k!='stages'}))
