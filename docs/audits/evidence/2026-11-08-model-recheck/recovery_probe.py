"""Isolated component experiment: real SQLite, Worker.run, checkpointing and local HTTP524.
Synthetic podcast processor replaces acquisition/transcription/generation; no production access.
"""
import os,sys,json,subprocess,threading,tempfile,time
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
ROOT=Path('/workspace/model-recovery-audit');sys.path.insert(0,str(ROOT))
DATA=Path('/workspace/model-recheck-private/recovery-data')
os.environ['XYZ_DATA_DIR']=str(DATA)
for k in ('SUPABASE_URL','SUPABASE_KEY','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_ANON_KEY'):os.environ[k]=''
os.environ['DURABLE_PROCESSING_ENABLED']='true'
if len(sys.argv)>1:
 import config
 assert not config.USE_SUPABASE
 from execution_store import Store
 from processing_execution import Execution,checkpoint_call
 from api.worker import Worker
 from api.routers import processing
 from api.schemas import ProcessingStatus
 import requests
 store=Store(DATA/'queue.sqlite');processing.JOBS_FILE=DATA/'jobs.json'
 processing.jobs={};processing._load_jobs_from_file()
 phase=sys.argv[1];port=sys.argv[2]
 def enqueue(task):
  processing.jobs[task]=ProcessingStatus(job_id=task,user_id='synthetic-recovery',status='pending',source_url='http://127.0.0.1:'+port+'/'+task)
  processing._save_jobs_to_file()
  return store.enqueue('synthetic-recovery','podcast',task,'source:'+task,{'episode_url':'http://127.0.0.1:'+port+'/'+task,'user_id':'synthetic-recovery'})
 def synthetic_processor(task,episode_url,**kwargs):
  checkpoint_call('synthetic-transcript',task,lambda:{'text':'synthetic source '+task})
  def call():
   r=requests.get(episode_url,timeout=5);r.raise_for_status();return r.json()
  checkpoint_call('synthetic-model',task,call)
  processing.update_job_status(task,'completed',100,'Synthetic probe complete')
 processing.process_episode_sync=synthetic_processor
 worker=Worker(store=store,slots=1)
 if phase=='first':enqueue('a');enqueue('b')
 if phase=='retry':enqueue('a')
 results=[]
 if phase in ('first','retry'):
  while row:=store.claim(worker.ident):
   worker.run(row,Execution(row['user_id'],row['source_id'],store,queue_id=row['id'],lease_owner=worker.ident))
   results.append({'task':row['task_id'],'state':store.latest(row['user_id'],'podcast',row['task_id'])['state']})
  processing._save_jobs_to_file()
 else:
  assert processing.jobs['a'].status==processing.jobs['b'].status=='completed'
  assert store.claim(worker.ident) is None
  from processing_execution import bind
  for task in ['a','b']:
   with bind(Execution('synthetic-recovery','source:'+task,store)):
    value=checkpoint_call('synthetic-model',task,lambda: (_ for _ in ()).throw(AssertionError('Completed checkpoint regenerated')))
    assert value=={'synthetic':True}
  results=[{'new_process_restored_completed_jobs':True,'saved_model_checkpoints_reused_without_HTTP':True}]
 worker.stop();(DATA/(phase+'.json')).write_text(json.dumps(results));sys.exit(0)
DATA.mkdir(parents=True,exist_ok=False)
counts={'a':0,'b':0}
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  key=self.path.strip('/');counts[key]+=1
  status=524 if key=='a' and counts[key]==1 else 200
  body=json.dumps({'synthetic':True}).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
for phase in ['first','retry','restart']:
 subprocess.run([sys.executable,__file__,phase,str(server.server_port)],cwd=ROOT,check=True,timeout=45,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
first=json.loads((DATA/'first.json').read_text());retry=json.loads((DATA/'retry.json').read_text());restart=json.loads((DATA/'restart.json').read_text())
assert first==[{'task':'a','state':'failed'},{'task':'b','state':'completed'}]
assert retry==[{'task':'a','state':'completed'}]
assert counts=={'a':2,'b':1}
server.shutdown()
result={'status':'PASS','first':first,'explicit_retry':retry,'fresh_process':restart,'local_http_counts':counts,'scope':'Real SQLite and application Worker.run/checkpoint/job persistence;synthetic processor and loopback HTTP524;manual claim/dispatch;three separate Python processes','limitations':['Not real upstream524','Not full API server restart or browser acceptance','Not full podcast acquisition/transcription/model pipeline','Not production Supabase','Not a killed-worker lease-expiry test']}
Path('/workspace/model-recheck-private/recovery.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
