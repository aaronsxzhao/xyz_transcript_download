import os,json,threading,subprocess,time,signal
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import requests
root=Path('/workspace/acceptance-nov09-private');count={};hold=threading.Event();release=threading.Event()
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  count[self.path]=count.get(self.path,0)+1;n=count[self.path]
  if self.path=='/a' and n==2:hold.set();release.wait(180)
  body=b'{"saved":"synthetic-only"}';self.send_response(524 if self.path=='/a' and n==1 else 200);self.send_header('Content-Length',str(len(body)));self.end_headers()
  try:self.wfile.write(body)
  except BrokenPipeError:pass
 def log_message(self,*a):pass
fixture=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=fixture.serve_forever,daemon=True).start()
base='http://127.0.0.1:18791';log=(root/'isolated-server.log').open('a');proc=None
s=requests.Session();s.trust_env=False
out={}
def start():
 p=subprocess.Popen(['/workspace/xyz_transcript_download/venv/bin/python',str(root/'isolation-server-v2.py')],cwd='/workspace/full-acceptance',env={**os.environ,'AUDIT_FIXTURE_PORT':str(fixture.server_port)},stdout=log,stderr=log)
 for _ in range(100):
  try:
   if s.get(base+'/api/health',timeout=1).status_code==200:return p
  except requests.RequestException:pass
  assert p.poll() is None
  time.sleep(.2)
 raise AssertionError('Server startup timeout')
def post(path,data=None):
 r=s.post(base+path,json=data,timeout=15);assert r.status_code==200,(path,r.status_code);return r.json()
def wait(job,state,seconds=120):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  r=s.get(base+'/api/jobs/'+job,timeout=5);assert r.status_code==200
  if r.json()['status']==state:return r.json()
  time.sleep(1)
 raise AssertionError('Status deadline')
try:
 proc=start();a=post('/api/process',{'episode_url':'local://a'})['job_id'];wait(a,'failed');out['injected_524_failed_job']=True
 b=post('/api/process',{'episode_url':'local://b'})['job_id'];wait(b,'completed');out['next_job_completed']=True
 retry=post('/api/jobs/'+a+'/retry')['new_job_id'];assert hold.wait(20);out['explicit_retry_reached_upstream']=True
 os.kill(proc.pid,signal.SIGKILL);proc.wait(timeout=5);release.set();out['actual_api_process_sigkill']=True
 proc=start();assert s.get(base+'/api/jobs/'+b).json()['status']=='completed';out['completed_job_restored']=True
 restored=wait(retry,'completed',seconds=115);out['retry_recovered_after_real_90_second_lease']=True
 rows=[json.loads(x) for x in (root/'service-v2-data/preparations.jsonl').read_text().splitlines()];assert len(rows)==2;out['prepared_source_not_repeated']=True
 assert count['/a']==3 and count['/b']==1;out['fixture_calls']=count;out['status']='PASS'
except Exception as e:out.update(status='FAIL',error_type=type(e).__name__,error_line=__import__('traceback').extract_tb(e.__traceback__)[-1].lineno)
finally:
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=15)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
 fixture.shutdown();log.close();(root/'service-recovery-v2.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
