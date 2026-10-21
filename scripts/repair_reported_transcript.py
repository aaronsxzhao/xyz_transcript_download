"""Repair only the reported incomplete transcript through the deployed owner API.

Credentials stay in memory. Reports contain only durations, counts and statuses.
Healthy content is never regenerated on subsequent deployment checks.
"""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
EPISODE_ID = '6ad08b370e4e410a05bd4fd0'


def repair(settings):
    from api.supabase_client import get_supabase_admin_client
    from jose import jwt
    client=get_supabase_admin_client()
    rows=client.table('episodes').select('eid,user_id,duration').eq('eid',EPISODE_ID).limit(2).execute().data
    if len(rows)!=1: raise RuntimeError('Ambiguous or missing reported episode')
    episode=rows[0]
    owner=episode['user_id']
    def health():
        rows=client.table('transcripts').select('duration,text').eq('episode_id',EPISODE_ID).eq('user_id',owner).execute().data
        summaries=client.table('summaries').select('topics').eq('episode_id',EPISODE_ID).eq('user_id',owner).execute().data
        row=rows[0] if rows else {}
        return {'expected_seconds':episode['duration'],'transcript_seconds':round(row.get('duration') or 0),
                'transcript_chars':len(row.get('text') or ''),'topics':len(summaries[0].get('topics') or []) if summaries else 0}
    def valid(report):
        return report['transcript_seconds']>=report['expected_seconds']*.85 and report['transcript_chars']>=100 and report['topics']>0
    before=health()
    if valid(before): return {'repair':'reported_transcript','status':'already_healthy',**before}
    now=int(time.time())
    token=jwt.encode({'sub':owner,'aud':'authenticated','role':'authenticated','iat':now,'exp':now+1200},settings['SUPABASE_JWT_SECRET'],algorithm='HS256')
    def request(path,data=None):
        headers={'Authorization':'Bearer '+token}
        if data is not None: headers['Content-Type']='application/json'
        req=urllib.request.Request('https://aipodcastsummary.online'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)
    expected=os.environ.get('EXPECTED_REVISION')
    if expected and request('/api/health').get('revision')!=expected: raise RuntimeError('Expected release is not live')
    # Same supported regeneration action as the reader. The new pipeline detects
    # incomplete cached transcripts and transcribes the entire recording again.
    active=[item for item in request('/api/jobs').get('jobs',[]) if item.get('episode_id')==EPISODE_ID
            and item.get('status') in {'pending','fetching','downloading','transcribing','summarizing'}]
    job_id=active[0]['job_id'] if active else request(f'/api/episodes/{EPISODE_ID}/resummarize',{})['job_id']
    previous=None
    for _ in range(72):
        status=request('/api/jobs/'+job_id)['status']
        if status!=previous:
            print(json.dumps({'repair':'reported_transcript','status':status}),flush=True)
            previous=status
        if status=='completed':
            after=health()
            if not valid(after): raise RuntimeError('Repaired transcript did not pass completeness checks')
            return {'repair':'reported_transcript','status':'repaired',**after}
        if status in {'failed','cancelled'}: raise RuntimeError('Reported transcript processing failed')
        time.sleep(10)
    raise TimeoutError('Reported transcript repair is still running')


def main():
    from scripts.diagnose_deployment import oci_json
    instance=oci_json(['container-instances','container-instance','get','--container-instance-id',os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"')
    for container_id in instance or []:
        settings=oci_json(['container-instances','container','get','--container-id',container_id], 'data."environment-variables"') or {}
        if not settings.get('SUPABASE_JWT_SECRET'): continue
        bindings={key:value for key,value in settings.items() if key.startswith('SUPABASE_') or key=='USE_SUPABASE'}
        with tempfile.TemporaryDirectory() as directory:
            os.environ.update(bindings)
            os.environ['XYZ_DATA_DIR']=directory
            os.environ['DISCORD_WEBHOOK_URL']=''
            logging.disable(logging.CRITICAL)
            return repair(settings)
    raise RuntimeError('Application container not found')


if __name__=='__main__':
    try:
        print(json.dumps(main()))
    except Exception as exc:
        print(json.dumps({'repair':'reported_transcript','status':'failed','error_type':type(exc).__name__}))
        sys.exit(1)
