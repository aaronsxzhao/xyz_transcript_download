"""Import the user-requested public example once through the deployed owner API.

No LLM calls, settings changes or existing note regeneration. The article stays
in its owner's Library. Logs contain numeric/boolean verification only.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
EXAMPLE = 'https://blog.samaltman.com/how-to-be-successful'


def submit(token):
    command = ['curl','--silent','--show-error','--compressed','--max-time','30','--header','@-',
               '--write-out','\n%{http_code}']
    for key,value in {'url':EXAMPLE,'platform':'web','style':'original','formats':'["original"]'}.items():
        command += ['--data-urlencode',key+'='+value]
    command += ['https://aipodcastsummary.online/api/video-notes/generate']
    result = subprocess.run(command,input='Authorization: Bearer '+token+'\n',capture_output=True,text=True,timeout=35)
    body,_,status = result.stdout.rpartition('\n')
    if result.returncode or status != '200': raise RuntimeError('Public article submission failed')
    return json.loads(body)['task_id']


def verify():
    from jose import jwt
    from api.supabase_client import get_supabase_admin_client
    from scripts.repair_reported_transcript import request_json
    db = get_supabase_admin_client()
    owners = db.table('video_tasks').select('user_id').eq('id','bc2c988b-2b4').limit(1).execute().data or []
    if len(owners) != 1 or not owners[0].get('user_id'):
        raise RuntimeError('Requested example owner is unavailable')
    now = int(time.time())
    token = jwt.encode({'sub':owners[0]['user_id'],'aud':'authenticated','role':'authenticated','iat':now,'exp':now+300},os.environ['SUPABASE_JWT_SECRET'],algorithm='HS256')
    existing = request_json('/api/video-notes/submission?'+urlencode({'url':EXAMPLE,'platform':'web'}),token)
    created = not bool(existing.get('task_id'))
    ident = submit(token) if created else existing['task_id']
    deadline = time.monotonic()+120
    while True:
        task = request_json('/api/video-notes/tasks/'+ident+'?view=note',token)
        if task.get('status') == 'success': break
        if task.get('status') in ('failed','cancelled'):
            raise RuntimeError('Public article processing did not complete')
        if time.monotonic() >= deadline: raise TimeoutError('Public article verification timed out')
        time.sleep(2)
    source = task.get('source_metadata') or {}
    assert task.get('platform') == 'web' and task.get('style') == 'original'
    assert not task.get('model') and not task.get('transcript')
    assert source.get('type') == 'article' and source.get('access') == 'complete'
    assert len(task.get('markdown') or '') > 5000 and task.get('versions')
    page = request_json('/api/library?'+urlencode({'kind':'article','ids':'video:'+ident}),token)
    assert any(row['id']==ident and row['content_type']=='article' for row in page['items'])
    return {'public_article_verification':True,'created':created,'original_characters':len(task['markdown']),
            'versions':len(task['versions']),'no_llm':True,'library_article_filter':True}


if __name__ == '__main__':
    from scripts.repair_source_coverage import main
    try:
        print(json.dumps(main(verify)))
    except Exception as error:
        print(json.dumps({'public_article_verification':False,'error_type':type(error).__name__}))
        raise SystemExit(1)
