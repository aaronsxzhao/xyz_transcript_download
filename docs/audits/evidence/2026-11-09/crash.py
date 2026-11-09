"""Real child-process death and lease recovery; isolated SQLite component experiment."""
import sys,os,json,subprocess,tempfile,time,signal
from pathlib import Path
repo=Path('/workspace/audit-nov09');sys.path.insert(0,str(repo))
root=Path('/workspace/audit-nov09-private/crash-data');root.mkdir(exist_ok=True)
os.environ['XYZ_DATA_DIR']=str(root)
from execution_store import Store
from processing_execution import Execution,bind,checkpoint_call
s=Store(root/'queue.sqlite')
if len(sys.argv)>1:
 row=s.claim('killed-worker',lease=2)
 with bind(Execution('synthetic','source',s,queue_id=row['id'],lease_owner='killed-worker')):
  checkpoint_call('completed-section','one',lambda:{'text':'synthetic checkpoint'})
 (root/'ready').write_text(row['id'])
 while True:time.sleep(.1)
s.enqueue('synthetic','podcast','crash-task','source',{})
p=subprocess.Popen([sys.executable,__file__,'child'],cwd=repo)
deadline=time.monotonic()+10
while not (root/'ready').exists():
 assert time.monotonic()<deadline and p.poll() is None
 time.sleep(.05)
old=(root/'ready').read_text();os.kill(p.pid,signal.SIGKILL);p.wait(timeout=5)
assert p.returncode==-signal.SIGKILL
assert s.claim('new-worker') is None # still leased, no double execution
while True:
 row=s.claim('new-worker')
 if row:break
 assert time.monotonic()<deadline
 time.sleep(.1)
assert row['id']==old and row['attempts']==2
assert not s.finish(old,'killed-worker','completed',{})
assert s.heartbeat(old,'killed-worker',{}) is None
with bind(Execution('synthetic','source',s,queue_id=old,lease_owner='new-worker')):
 result=checkpoint_call('completed-section','one',lambda:(_ for _ in ()).throw(AssertionError('Duplicate generation')))
assert result=={'text':'synthetic checkpoint'}
assert s.finish(old,'new-worker','completed',{})
assert Store(root/'queue.sqlite').latest('synthetic','podcast','crash-task')['state']=='completed'
r={'status':'PASS','actual_child_sigkill':True,'pre_expiry_claim_blocked':True,'same_work_reclaimed_after_real_expiry':True,'attempts':2,'old_worker_finish_rejected':True,'old_worker_heartbeat_rejected':True,'completed_checkpoint_reused_without_generator':True,'completion_persisted':True,'test_lease_seconds':2,'scope':'real process kill;application Store/Execution;SQLite;synthetic content','limits':'Not full API-server restart,production90second lease,Supabase,model provider or UI lifecycle'}
(root.parent/'crash.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
