"""Pause at durable boundaries before replacing the processing container.

Uses existing OCI bindings in memory. No keys, task payloads or source text are
printed. On first rollout, legacy work must finish before restart is allowed.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from scripts.diagnose_deployment import oci_json


def bindings():
    ids=oci_json(['container-instances','container-instance','get','--container-instance-id',os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"')
    for ident in ids or []:
        value=oci_json(['container-instances','container','get','--container-id',ident],'data."environment-variables"') or {}
        if value.get('SUPABASE_SERVICE_KEY') and value.get('SUPABASE_URL'):
            return value['SUPABASE_URL'].rstrip('/'),value['SUPABASE_SERVICE_KEY']
    raise RuntimeError('Application database binding is unavailable')


def run(operation):
    base,key=bindings()
    revision=os.environ['EXPECTED_REVISION']
    def rest(table,filters=None,method='GET',body=None):
        query='?'+urlencode(filters or {})
        request=Request(base+'/rest/v1/'+table+query,method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'})
        with urlopen(request,timeout=20) as response:
            raw=response.read()
            return json.loads(raw) if raw else []
    if operation=='end':
        rest('processing_controls',{'name':'eq.drain_embedded','target_revision':'eq.'+revision},'DELETE')
        return
    now=datetime.now(timezone.utc)
    rest('processing_controls',method='POST',body={'name':'drain_embedded','target_revision':revision,'expires_at':(now+timedelta(minutes=15)).isoformat()})
    deadline=time.monotonic()+480
    while time.monotonic()<deadline:
        active=rest('processing_work',{'select':'id','state':'eq.running','worker_group':'eq.embedded','lease_until':'gt.'+datetime.now(timezone.utc).isoformat()})
        # Before the first durable rollout, active work has no queue record.
        legacy=rest('processing_jobs',{'select':'id','payload->>status':'in.(pending,fetching,downloading,transcribing,summarizing,saving,cancelling)','updated_at':'gt.'+(now-timedelta(minutes=20)).isoformat()})
        video=rest('video_tasks',{'select':'id','status':'in.(pending,parsing,downloading,transcribing,summarizing,saving,cancelling)','updated_at':'gt.'+(now-timedelta(minutes=20)).isoformat()})
        tracked=rest('processing_work',{'select':'task_id','task_id':'in.('+','.join(row['id'] for row in legacy+video)+')'}) if legacy or video else []
        tracked_ids={row['task_id'] for row in tracked}
        untracked=sum(row['id'] not in tracked_ids for row in legacy+video)
        print(json.dumps({'drain_active_leases':len(active),'legacy_active':untracked}),flush=True)
        if not active and not untracked:return
        time.sleep(5)
    raise RuntimeError('Processing has not reached a saved boundary; restart was blocked')


if __name__=='__main__':
    try: run(sys.argv[1])
    except Exception as error:
        print(json.dumps({'processing_drain_failed':True,'error_type':type(error).__name__}),flush=True)
        raise SystemExit(1)
