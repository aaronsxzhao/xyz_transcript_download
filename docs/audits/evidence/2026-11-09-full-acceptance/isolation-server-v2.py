import os,sys,json
from pathlib import Path
sys.path.insert(0,'/workspace/full-acceptance')
root=Path('/workspace/acceptance-nov09-private/service-v2-data');root.mkdir(exist_ok=True)
os.environ.update(XYZ_DATA_DIR=str(root),PROCESSING_DURABLE_QUEUE='1',SUPABASE_URL='',SUPABASE_KEY='',SUPABASE_ANON_KEY='',SUPABASE_SERVICE_ROLE_KEY='')
import config
assert not config.USE_SUPABASE
from api.routers import processing
from processing_execution import checkpoint_call
import requests
# Only the expensive provider/media processor is replaced, inside this isolated process.
def synthetic(job_id,episode_url,**kwargs):
 def prepare():
  with (root/'preparations.jsonl').open('a') as f:f.write(json.dumps({'source':episode_url})+'\n')
  return {'prepared':True}
 checkpoint_call('audit-source',episode_url,prepare)
 processing.update_job_status(job_id,'summarizing',75,'Isolated HTTP fixture')
 def provider():
  r=requests.get('http://127.0.0.1:'+os.environ['AUDIT_FIXTURE_PORT']+'/'+episode_url.removeprefix('local://'),timeout=180);r.raise_for_status();return r.json()
 checkpoint_call('audit-result',episode_url,provider)
 processing.update_job_status(job_id,'completed',100,'Isolated fixture saved')
processing.process_episode_sync=synthetic
from api.main import app
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=18791,log_level='error')
