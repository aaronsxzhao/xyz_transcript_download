"""Durable dispatcher. Embedded today; `python -m api.worker` runs independently.

Leases expire after a killed process; actual provider responses are checkpointed.
A lease is renewed before committing source/final content. Queue payloads contain
request parameters only, never credentials; credentials are resolved per owner.
"""
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from execution_store import get_store
from processing_execution import Execution, ProcessingPaused, bind
from logger import get_logger

logger = get_logger('processing_worker')
TERMINAL = {'completed','failed','cancelled','success'}


def podcast_payload(job):
    return {key:getattr(job,key) for key in ('source_url','transcribe_only','user_id','whisper_model','llm_model','resummarize','force')}


class Worker:
    def __init__(self,store=None,group='embedded',slots=2):
        self.store=store or get_store()
        self.group=group
        self.revision=os.environ.get('APP_REVISION','development')
        self.ident=str(uuid.uuid4())
        self.slots=slots
        self.stop_event=threading.Event()
        self.pool=ThreadPoolExecutor(max_workers=slots,thread_name_prefix='durable_content')
        self.active={}
        self.thread=None
        self.last_poll=time.monotonic()

    def start(self):
        self.thread=threading.Thread(target=self.loop,name='durable_dispatcher',daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        for _,execution in list(self.active.values()): execution.pause_requested=True
        if self.thread: self.thread.join(timeout=5)
        self.pool.shutdown(wait=False,cancel_futures=True)

    def adopt(self):
        """Recover admission saved before a request died, including legacy jobs."""
        from api.routers import processing
        from api.job_persistence import restore_jobs, save_job
        from api.schemas import ProcessingStatus
        from config import USE_SUPABASE
        # Legacy jobs.json is still loaded on startup. Cloud-only recovery used
        # to leave these visible as Queued forever without ever admitting them.
        with processing._jobs_lock:
            retained={job.job_id:job.model_dump() for job in processing.jobs.values()}
        if USE_SUPABASE:
            retained.update({row['job_id']:row for row in restore_jobs()})
        rows=list(retained.values())
        for data in rows:
            job=ProcessingStatus(**data)
            if job.status in TERMINAL: continue
            if USE_SUPABASE and not job.user_id:
                processing.jobs[job.job_id]=job
                processing.update_job_status(job.job_id,'failed',0,
                    'This older task has no saved account. Open the original source and process it again.')
                continue
            if job.status == 'cancelling':
                processing.jobs[job.job_id]=job
                processing.update_job_status(job.job_id,'cancelled',0,'Cancelled')
                continue
            existing=self.store.latest(job.user_id,'podcast',job.job_id)
            # A terminal durable record must never be automatically re-enqueued.
            if existing: continue
            processing.jobs[job.job_id]=job
            if not job.source_url:
                processing.update_job_status(job.job_id,'failed',0,
                    'This older task has no saved source link and cannot resume. Open the original episode and process it again.')
                continue
            if USE_SUPABASE:
                save_job(job)
            payload=podcast_payload(job);payload['episode_url']=payload.pop('source_url')
            self.store.enqueue(job.user_id,'podcast',job.job_id,'podcast:'+(job.checkpoint_root or job.job_id),payload)
        if USE_SUPABASE:
            # One bounded query for active rows, no media/transcript payload download.
            from api.supabase_client import get_supabase_admin_client
            tasks=get_supabase_admin_client().table('video_tasks').select('id,user_id,url,platform,style,formats,quality,model,extras,video_quality,video_understanding,video_interval,grid_cols,grid_rows,status,updated_at').in_('status',['pending','parsing','downloading','transcribing','summarizing','saving','cancelling']).limit(500).execute().data or []
        else:
            from video_task_db import get_video_task_db
            tasks=[t for t in get_video_task_db().list_tasks() if t['status'] not in TERMINAL and t['status']!='discovered']
        for task in tasks:
            if task['status']=='cancelling':
                from video_task_db import get_video_task_db
                get_video_task_db().update_task(task['id'],{'status':'cancelled','message':'Cancelled'})
                continue
            existing=self.store.latest(task['user_id'],'video',task['id'])
            if existing:
                # A request can die after resetting the domain row but before
                # enqueueing its new attempt. Only a newer explicit pending
                # state reopens a terminal queue record.
                from datetime import datetime
                def timestamp(value):
                    if isinstance(value,(int,float)): return value
                    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp() if value else 0
                if existing['state'] in ('queued','running') or task['status']!='pending' or timestamp(task.get('updated_at'))<=timestamp(existing['updated_at']): continue
            payload={key:task.get(key,default) for key,default in dict(url='',platform='',style='detailed',formats=['toc','summary','screenshot'],quality='medium',extras='',video_understanding=False,video_interval=4,grid_cols=3,grid_rows=3,video_quality='720',user_id=None).items()}
            payload['llm_model']=task.get('model') or ''
            self.store.enqueue(task['user_id'],'video',task['id'],'video:'+task['id']+(':'+str(uuid.uuid4()) if existing else ''),payload)

    def loop(self):
        last_adopt=0
        last_prune=0
        while not self.stop_event.is_set():
            try:
                now=time.monotonic()
                if now-last_adopt>30:
                    try: self.adopt()
                    except Exception as error: logger.warning('Admission recovery temporarily unavailable: %s',type(error).__name__)
                    last_adopt=now
                if now-last_prune>86400:
                    # Checkpoint housekeeping must never stop queue dispatch.
                    try: self.store.prune()
                    except Exception as error: logger.warning('Checkpoint cleanup temporarily unavailable: %s',type(error).__name__)
                    last_prune=now
                control=self.store.control()
                for key,(future,execution) in list(self.active.items()):
                    if future.done():
                        try: future.result()
                        except BaseException as error: logger.warning('Worker attempt ended: %s',type(error).__name__)
                        self.active.pop(key,None)
                        continue
                    row=self.store.heartbeat(key,self.ident,execution.snapshot())
                    if row is None: execution.lease_lost=True
                    elif row.get('cancel_requested'):
                        execution.cancelled=True
                        execution.deleted=bool(row['payload'].get('deleted'))
                    if control and self.group=='embedded' and control['target_revision']!=self.revision:
                        execution.pause_requested=True
                while len(self.active)<self.slots and not self.stop_event.is_set():
                    row=self.store.claim(self.ident,self.group,self.revision)
                    if not row: break
                    execution=Execution(row['user_id'],row['source_id'],self.store,queue_id=row['id'],lease_owner=self.ident)
                    previous=row.get('metrics') or {}
                    execution.metrics=previous.get('stages',{})
                    execution.hits=previous.get('checkpoint_hits',0)
                    execution.previous_wall=previous.get('wall_seconds',0)
                    future=self.pool.submit(self.run,row,execution)
                    self.active[row['id']]=(future,execution)
                self.last_poll=time.monotonic()
            except Exception as error:
                logger.warning('Durable dispatcher temporarily unavailable: %s',type(error).__name__)
            self.stop_event.wait(3)

    def run(self,row,execution):
        state='failed'
        task=row['task_id'];kind=row['kind'];owner=row['user_id']
        try:
            if row['state']!='running':
                self.sync_terminal(row,'cancelled' if row.get('cancel_requested') else 'failed')
                return
            with bind(execution):
                if kind=='podcast':
                    from api.routers import processing
                    from api.job_persistence import restore_jobs
                    from api.schemas import ProcessingStatus
                    if task not in processing.jobs:
                        saved=next((job for job in restore_jobs() if job['job_id']==task and job.get('user_id')==owner),None)
                        if not saved: state='cancelled';return
                        processing.jobs[task]=ProcessingStatus(**saved)
                    payload={key:value for key,value in row['payload'].items() if key!='deleted'}
                    if row['attempts']>1: payload['force']=False
                    processing.process_episode_sync(task,**payload)
                    state=processing.jobs[task].status
                else:
                    from api.routers.video_notes import process_video_note_sync
                    from video_task_db import get_video_task_db
                    payload={key:value for key,value in row['payload'].items() if key not in ('deleted','attempt_id')}
                    process_video_note_sync(task,**payload)
                    current=get_video_task_db().get_task(task,owner)
                    state=current['status'] if current else 'cancelled'
                state='completed' if state in ('success','completed') else 'cancelled' if execution.cancelled or state=='cancelled' else 'failed'
        except ProcessingPaused:
            state='queued'
        except Exception as error:
            logger.warning('Processing attempt failed: kind=%s error=%s',kind,type(error).__name__)
            state='cancelled' if execution.cancelled else 'failed'
            self.sync_terminal(row,state)
        finally:
            if row['state']=='running':
                try: self.store.finish(row['id'],self.ident,state,execution.snapshot())
                except Exception: logger.warning('Could not release processing lease; expiry will recover it')

    def sync_terminal(self,row,state):
        if row['payload'].get('deleted'): return
        message='Cancelled' if state=='cancelled' else 'Processing was repeatedly interrupted. Retry to reuse completed segments.'
        if row['kind']=='podcast':
            from api.routers import processing
            from api.job_persistence import restore_jobs
            from api.schemas import ProcessingStatus
            if row['task_id'] not in processing.jobs:
                saved=next((job for job in restore_jobs() if job['job_id']==row['task_id'] and job.get('user_id')==row['user_id']),None)
                if saved: processing.jobs[row['task_id']]=ProcessingStatus(**saved)
            processing.update_job_status(row['task_id'],state,0,message)
        else:
            from video_task_db import get_video_task_db
            get_video_task_db().update_task(row['task_id'],{'status':state,'message':message})


if __name__=='__main__':
    import signal
    worker=Worker(group='worker').start()
    signal.signal(signal.SIGTERM,lambda *_:worker.stop_event.set())
    signal.signal(signal.SIGINT,lambda *_:worker.stop_event.set())
    try:
        while not worker.stop_event.wait(1): pass
    finally: worker.stop()
