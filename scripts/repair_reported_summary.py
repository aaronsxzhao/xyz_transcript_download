"""Recover the reported Groq summary from its saved transcript using its owner API.

Reports contain fixed labels and numeric counts, never source text or credentials.
"""
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.repair_reported_transcript import request_json

EPISODE_ID='6ad0a61f0e4e410a05bd5f13'
JOB_ID='69a4138f-a12f-4354-bec9-c988c0a62814'


def repair(settings):
    from api.supabase_client import get_supabase_admin_client
    from jose import jwt
    client=get_supabase_admin_client()
    jobs=client.table('processing_jobs').select('user_id,payload').eq('id',JOB_ID).execute().data
    if not jobs:
        return {'repair':'reported_summary','status':'reported_task_already_dismissed'}
    if len(jobs)!=1 or jobs[0]['payload'].get('episode_id')!=EPISODE_ID:
        raise RuntimeError('Reported task unavailable')
    owner=jobs[0]['user_id']
    transcripts=client.table('transcripts').select('id,duration,text').eq('user_id',owner).eq('episode_id',EPISODE_ID).execute().data
    if len(transcripts)!=1 or (transcripts[0].get('duration') or 0)<5000 or len(transcripts[0].get('text') or '')<1000:
        raise RuntimeError('Saved transcript is incomplete')
    original=transcripts[0]
    now=int(time.time())
    token=jwt.encode({'sub':owner,'aud':'authenticated','role':'authenticated','iat':now,'exp':now+1500},settings['SUPABASE_JWT_SECRET'],algorithm='HS256')
    def request(path,data=None):return request_json(path,token,data)
    def checked_summary():
        try:return request('/api/summaries/'+EPISODE_ID)
        except Exception as error:
            if getattr(error,'http_status',0)==404:return None
            raise
    def valid(summary):return bool(summary and len(summary.get('overview',''))>=100 and summary.get('key_points') and summary.get('topics') and not summary.get('quality_warning'))
    expected=os.environ.get('EXPECTED_REVISION')
    if expected and request('/api/health').get('revision')!=expected:
        raise RuntimeError('Expected release is not live')
    summary=checked_summary()
    if not valid(summary):
        active=[job for job in request('/api/jobs').get('jobs',[]) if job.get('episode_id')==EPISODE_ID and job.get('status') not in {'failed','cancelled','completed'}]
        job_id=active[0]['job_id'] if active else request('/api/jobs/'+JOB_ID+'/retry',{})['new_job_id']
        previous=None
        for _ in range(120):
            job=request('/api/jobs/'+job_id)
            status=job['status']
            if status!=previous:
                print(json.dumps({'repair':'reported_summary','status':status}),flush=True)
                previous=status
            if status=='completed':break
            if status in {'failed','cancelled'}:raise RuntimeError('Summary recovery did not complete')
            time.sleep(5)
        else:raise TimeoutError('Summary recovery is still processing')
        summary=checked_summary()
    if not valid(summary):raise RuntimeError('Recovered summary is incomplete')
    after=client.table('transcripts').select('id,duration,text').eq('user_id',owner).eq('episode_id',EPISODE_ID).execute().data
    if len(after)!=1 or after[0]!=original:raise RuntimeError('Saved transcript changed during summary recovery')
    # The failed attempt is acknowledged only after the new summary is verified.
    old=request('/api/jobs/'+JOB_ID)
    if old['status']=='failed':
        request_json_delete('/api/jobs/'+JOB_ID,token)
    return {'repair':'reported_summary','status':'verified','transcript_unchanged':1,'transcript_seconds':round(original['duration']),
            'topics':len(summary['topics']),'key_points':len(summary['key_points'])}


def request_json_delete(path,token):
    import subprocess
    result=subprocess.run(['curl','--silent','--show-error','--max-time','30','--request','DELETE','--header','@-','--output',os.devnull,'--write-out','%{http_code}',
                           'https://aipodcastsummary.online'+path],input='Authorization: Bearer '+token+'\n',capture_output=True,text=True,timeout=35)
    if result.returncode or result.stdout!='200':raise RuntimeError('Failed task acknowledgement unavailable')


def main():
    from scripts.diagnose_deployment import oci_json
    containers=oci_json(['container-instances','container-instance','get','--container-instance-id',os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"')
    for container_id in containers or []:
        settings=oci_json(['container-instances','container','get','--container-id',container_id], 'data."environment-variables"') or {}
        if not settings.get('SUPABASE_JWT_SECRET'):continue
        with tempfile.TemporaryDirectory() as directory:
            os.environ.update({key:value for key,value in settings.items() if key.startswith('SUPABASE_') or key=='USE_SUPABASE'})
            os.environ['XYZ_DATA_DIR']=directory
            logging.disable(logging.CRITICAL)
            return repair(settings)
    raise RuntimeError('Application database binding unavailable')

if __name__=='__main__':
    try: print(json.dumps(main()))
    except Exception as error:
        print(json.dumps({'repair':'reported_summary','status':'failed','error_type':type(error).__name__}))
        sys.exit(1)
