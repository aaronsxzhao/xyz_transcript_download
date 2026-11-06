"""Isolated HTTP fault / persistence probe. Not browser or production acceptance.
Run with the repository on PYTHONPATH. Uses no real provider credential.
"""
import json, os, sys, time, tempfile, subprocess, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def database(root):
    from video_task_db import VideoTaskDB, _SQLiteVideoTaskDB
    db=VideoTaskDB.__new__(VideoTaskDB)
    db._backend=_SQLiteVideoTaskDB(root/'notes.sqlite')
    return db


def child(root):
    from execution_store import Store
    from processing_execution import Execution, bind, checkpoint_call
    store=Store(root/'queue.sqlite')
    work=store.enqueue('synthetic-owner','video','crash-task','crash-source',{})
    store.enqueue('synthetic-owner','video','next-task','next-source',{})
    row=store.claim('old-process',lease=2)
    with bind(Execution('synthetic-owner','crash-source',store)):
        checkpoint_call('completed-segment','segment-one',lambda:{'text':'synthetic saved segment'})
    db=database(root)
    db.create_task({'id':'saved-note','user_id':'synthetic-owner','platform':'youtube','title':'Synthetic crash probe'})
    db.complete_task('saved-note','# Synthetic saved note','detailed','fixture','synthetic-owner',version_id='version-one')
    (root/'ready.json').write_text(json.dumps({'work':work,'lease_until':row['lease_until']}))
    while True: time.sleep(1)


def main(root):
    from execution_store import Store
    from processing_execution import Execution, bind, checkpoint_call
    from note_summarizer import NoteSummarizer
    from config import MAX_RETRIES
    result={'scope':'isolated synthetic local HTTP + real SQLite + killed child process; no API/UI or production Supabase acceptance'}
    requests=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length',0)))
            status=524 if len(requests)<MAX_RETRIES else 200
            requests.append(status)
            body=({'error':{'message':'Synthetic injected 524','type':'synthetic_timeout'}} if status==524 else {'id':'fixture','object':'chat.completion','created':0,'model':'synthetic','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'# Synthetic recovery'}}]})
            raw=json.dumps(body).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    engine=NoteSummarizer(api_key='synthetic-local-only',base_url=f'http://127.0.0.1:{server.server_port}/v1',model='synthetic')
    store=Store(root/'http.sqlite')
    started=time.monotonic()
    try:
        with bind(Execution('synthetic-owner','http-source',store)):
            engine._call_llm('Synthetic fixture','Return synthetic content')
        raise AssertionError('Expected injected 524 exhaustion')
    except Exception as error:
        assert getattr(error,'status_code',None)==524, type(error).__name__
    with store.connection() as conn:
        assert conn.execute('select count(*) from processing_checkpoints').fetchone()[0]==0
    with bind(Execution('synthetic-owner','http-source',Store(root/'http.sqlite'))):
        text=engine._call_llm('Synthetic fixture','Return synthetic content')
    count=len(requests)
    with bind(Execution('synthetic-owner','http-source',Store(root/'http.sqlite'))):
        assert engine._call_llm('Synthetic fixture','Return synthetic content')==text
    assert len(requests)==count==MAX_RETRIES+1
    result['injected_http524']={'statuses':requests,'retry_limit':MAX_RETRIES,'failed_response_checkpointed':False,'fresh_execution_recovered':True,'replay_extra_requests':0,'seconds':round(time.monotonic()-started,3),'limit':'Actual local HTTP 524 through existing _call_llm; not real provider timeout, full generation, UI retry or worker dispatcher'}
    engine.client.close();server.shutdown();server.server_close()
    process=subprocess.Popen([sys.executable,__file__,'child',str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+30
        while not (root/'ready.json').exists():
            assert process.poll() is None,'Child exited before persistence'
            assert time.monotonic()<deadline,'Child readiness timeout'
            time.sleep(.1)
        ready=json.loads((root/'ready.json').read_text())
        process.kill();process.wait(timeout=5)
        time.sleep(max(0,ready['lease_until']-time.time()+.1))
        reopened=Store(root/'queue.sqlite');claimed=reopened.claim('new-process')
        assert claimed['id']==ready['work'] and claimed['attempts']==2
        assert not reopened.finish(ready['work'],'old-process','completed',{})
        def forbidden(): raise AssertionError('Completed segment was regenerated')
        with bind(Execution('synthetic-owner','crash-source',reopened)):
            assert checkpoint_call('completed-segment','segment-one',forbidden)['text']=='synthetic saved segment'
        assert reopened.finish(claimed['id'],'new-process','completed',{})
        following=reopened.claim('new-process')
        assert following['task_id']=='next-task'
        assert reopened.finish(following['id'],'new-process','completed',{})
        db=database(root)
        assert db.get_task('saved-note','synthetic-owner')['markdown']=='# Synthetic saved note'
        assert len(db.get_versions('saved-note'))==1
        result['process_death']={'signal':'SIGKILL','exit_code':process.returncode,'lease_seconds':2,'reclaimed_attempt':claimed['attempts'],'stale_worker_commit_rejected':True,'saved_checkpoint_reused':True,'next_queued_task_completed':True,'saved_note_and_version_retained':True,'limit':'Queue primitives driven explicitly; not application server restart or full dispatcher loop'}
    finally:
        if process.poll() is None:process.kill();process.wait()
    import api.save_outbox as outbox
    outbox.ROOT=root/'outbox';outbox.USE_SUPABASE=False
    db.create_task({'id':'recover-note','user_id':'synthetic-owner','platform':'youtube','title':'Synthetic outbox probe'})
    db.update_task('recover-note',{'markdown':'original synthetic content','status':'saving'})
    with db._backend._conn() as conn:
        conn.execute("CREATE TRIGGER audit_failure BEFORE UPDATE ON video_tasks WHEN NEW.id='recover-note' BEGIN SELECT RAISE(ABORT, 'synthetic disk failure'); END")
        conn.commit()
    failed=False
    try:db.complete_task('recover-note','recovered synthetic content','detailed','fixture','synthetic-owner',version_id='recovery-one')
    except Exception:failed=True
    assert failed
    assert db.get_task('recover-note','synthetic-owner')['markdown']=='original synthetic content'
    assert db.get_versions('recover-note')==[]
    payload=outbox.pending('synthetic-owner','recover-note')
    with db._backend._conn() as conn:conn.execute('DROP TRIGGER audit_failure');conn.commit()
    db=database(root)
    state=db.recover_note('recover-note','synthetic-owner',db.get_task('recover-note','synthetic-owner')['updated_at'],payload)
    assert state=='busy',state
    db.update_task('recover-note',{'status':'failed'})
    state=db.recover_note('recover-note','synthetic-owner',db.get_task('recover-note','synthetic-owner')['updated_at'],payload)
    assert state=='applied',state
    again=db.recover_note('recover-note','synthetic-owner',db.get_task('recover-note','synthetic-owner')['updated_at'],payload)
    assert again=='already_saved' and len(db.get_versions('recover-note'))==1
    result['save_recovery']={'fault':'SQLite trigger abort on synthetic note update','original_retained':True,'active_save_recovery_rejected':True,'terminal_state_set_by_harness':True,'partial_version_absent':True,'reopened_database_recovery':state,'repeat_recovery':again,'versions':1,'limit':'Local storage facade; no browser or hosted RPC'}
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='child': child(Path(sys.argv[2]))
    else:
        with tempfile.TemporaryDirectory(prefix='audit-manual-') as directory:
            os.environ['XYZ_DATA_DIR']=directory
            main(Path(directory))
