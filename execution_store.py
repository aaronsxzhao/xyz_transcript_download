"""Private durable queue/checkpoint storage; no credentials enter work payloads."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path


def enabled():
    from config import USE_SUPABASE
    return os.environ.get('PROCESSING_DURABLE_QUEUE','1' if USE_SUPABASE else '0')=='1'


def role(): return os.environ.get('PROCESSING_ROLE','embedded')


class Store:
    def __init__(self,path=None,client=None):
        from config import USE_SUPABASE,DATABASE_PATH
        self.cloud=path is None and (client is not None or USE_SUPABASE)
        self.client=client
        self.path=Path(path or DATABASE_PATH)
        if self.cloud:
            if self.client is None:
                from api.supabase_client import get_supabase_admin_client
                self.client=get_supabase_admin_client()
            if self.client is None: raise RuntimeError('Processing storage unavailable')
        else:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.connection() as db:
                db.executescript('''
                create table if not exists processing_work (
                  id text primary key,user_id text not null,kind text not null,task_id text not null,
                  source_id text not null,payload text not null,state text not null default 'queued',
                  cancel_requested integer not null default 0,worker_id text,worker_group text,
                  lease_until real,attempts integer not null default 0,metrics text not null default '{}',
                  created_at real not null,updated_at real not null);
                create unique index if not exists processing_work_active_state on processing_work(user_id,kind,task_id,state) where state in ('queued','running');
                create table if not exists processing_checkpoints (
                  user_id text not null,source_id text not null,stage text not null,fingerprint text not null,
                  result text not null,created_at real not null,
                  primary key(user_id,source_id,stage,fingerprint));
                create table if not exists processing_controls(name text primary key,target_revision text not null,expires_at real not null);
                ''')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(str(self.path),timeout=10);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def row(row):
        if row is None: return None
        value=dict(row)
        for key in ('payload','metrics'):
            if isinstance(value.get(key),str): value[key]=json.loads(value[key])
        return value

    def latest(self,owner,kind,task):
        if self.cloud:
            rows=self.client.table('processing_work').select('*').eq('user_id',owner).eq('kind',kind).eq('task_id',task).order('created_at',desc=True).limit(1).execute().data or []
            return rows[0] if rows else None
        with self.connection() as db:
            return self.row(db.execute('select * from processing_work where user_id=? and kind=? and task_id=? order by created_at desc limit 1',(owner or 'local',kind,task)).fetchone())

    def enqueue(self,owner,kind,task,source,payload):
        if self.cloud:
            return self.client.rpc('enqueue_processing_work',{'p_user':owner,'p_kind':kind,'p_task':task,'p_source':source,'p_payload':payload}).execute().data
        import time
        now=time.time();ident=str(uuid.uuid4())
        with self.connection() as db:
            db.execute('begin immediate')
            row=db.execute("select id from processing_work where user_id=? and kind=? and task_id=? and state in ('queued','running') and not cancel_requested order by created_at desc limit 1",(owner or 'local',kind,task)).fetchone()
            if row:return row['id']
            db.execute('insert into processing_work(id,user_id,kind,task_id,source_id,payload,created_at,updated_at) values(?,?,?,?,?,?,?,?)',(ident,owner or 'local',kind,task,source,json.dumps(payload),now,now))
        return ident

    def claim(self,worker,group='embedded',revision='development',lease=90):
        if self.cloud:
            rows=self.client.rpc('claim_processing_work',{'p_worker':worker,'p_group':group,'p_revision':revision,'p_lease':lease}).execute().data or []
            return rows[0] if rows else None
        import time
        now=time.time()
        with self.connection() as db:
            db.execute('begin immediate')
            drain=db.execute("select * from processing_controls where name='drain_embedded' and expires_at>?",(now,)).fetchone()
            if group=='embedded' and drain and drain['target_revision']!=revision:return None
            row=db.execute("""select q.* from processing_work q where ((q.state='queued' and not q.cancel_requested) or (q.state='running' and q.lease_until<?))
              and not exists(select 1 from processing_work other where other.user_id=q.user_id and other.kind=q.kind and other.task_id=q.task_id and other.id<>q.id and other.state='running' and other.lease_until>=?)
              order by q.created_at,q.id limit 1""",(now,now)).fetchone()
            if not row:return None
            state='cancelled' if row['cancel_requested'] else 'failed' if row['attempts']>=3 else 'running'
            db.execute('update processing_work set state=?,worker_id=?,worker_group=?,lease_until=?,attempts=attempts+1,updated_at=? where id=?',(state,worker,group,now+lease,now,row['id']))
            return self.row(db.execute('select * from processing_work where id=?',(row['id'],)).fetchone())

    def heartbeat(self,ident,worker,metrics,lease=90):
        if self.cloud:
            rows=self.client.rpc('heartbeat_processing_work',{'p_id':ident,'p_worker':worker,'p_metrics':metrics,'p_lease':lease}).execute().data or []
            return rows[0] if rows else None
        import time
        now=time.time()
        with self.connection() as db:
            row=db.execute("update processing_work set lease_until=?,metrics=?,updated_at=? where id=? and worker_id=? and state='running' and lease_until>? returning *",(now+lease,json.dumps(metrics),now,ident,worker,now)).fetchone()
            return self.row(row)

    def finish(self,ident,worker,state,metrics):
        if state not in ('queued','completed','cancelled','failed'):raise ValueError('Invalid state')
        if self.cloud:
            return self.client.rpc('finish_processing_work',{'p_id':ident,'p_worker':worker,'p_state':state,'p_metrics':metrics}).execute().data
        import time
        now=time.time()
        with self.connection() as db:
            return db.execute("update processing_work set state=case when cancel_requested then 'cancelled' else ? end,attempts=case when ?='queued' then max(0,attempts-1) else attempts end,metrics=?,updated_at=?,worker_id=null,lease_until=null where id=? and worker_id=? and state='running' and lease_until>?",(state,state,json.dumps(metrics),now,ident,worker,now)).rowcount>0

    def cancel(self,owner,kind,task,deleted=False):
        if self.cloud:
            rows=self.client.table('processing_work').select('id,state,payload').eq('user_id',owner).eq('kind',kind).eq('task_id',task).in_('state',['queued','running']).execute().data or []
            for row in rows:
                patch={'cancel_requested':True}
                if row['state']=='queued':patch['state']='cancelled'
                if deleted:patch['payload']={**row['payload'],'deleted':True}
                self.client.table('processing_work').update(patch).eq('id',row['id']).eq('user_id',owner).execute()
            return
        with self.connection() as db:
            rows=db.execute("select id,state,payload from processing_work where user_id=? and kind=? and task_id=? and state in ('queued','running')",(owner or 'local',kind,task)).fetchall()
            for row in rows:
                payload=json.loads(row['payload'])
                if deleted:payload['deleted']=True
                db.execute('update processing_work set cancel_requested=1,state=?,payload=? where id=?',('cancelled' if row['state']=='queued' else 'running',json.dumps(payload),row['id']))

    def control(self):
        if self.cloud:
            rows=self.client.table('processing_controls').select('*').eq('name','drain_embedded').gt('expires_at',datetime.now(timezone.utc).isoformat()).limit(1).execute().data or []
            return rows[0] if rows else None
        import time
        with self.connection() as db:
            row=db.execute("select * from processing_controls where name='drain_embedded' and expires_at>?",(time.time(),)).fetchone()
            return dict(row) if row else None

    def get_checkpoint(self,owner,source,stage,key):
        try:
            cutoff=datetime.now(timezone.utc)-timedelta(days=30)
            if self.cloud:
                rows=self.client.table('processing_checkpoints').select('result').eq('user_id',owner).eq('source_id',source).eq('stage',stage).eq('fingerprint',key).gt('created_at',cutoff.isoformat()).limit(1).execute().data or []
                return rows[0]['result'] if rows else None
            with self.connection() as db:
                row=db.execute('select result from processing_checkpoints where user_id=? and source_id=? and stage=? and fingerprint=? and created_at>?',(owner or 'local',source,stage,key,cutoff.timestamp())).fetchone()
                return json.loads(row['result']) if row else None
        except Exception:
            from logger import get_logger
            get_logger('execution').warning('Checkpoint lookup unavailable; retaining normal processing')
            return None

    def put_checkpoint(self,owner,source,stage,key,result):
        try:
            raw=json.dumps(result,ensure_ascii=False)
            if len(raw.encode())>1000000:return
            if self.cloud:
                self.client.table('processing_checkpoints').upsert({'user_id':owner,'source_id':source,'stage':stage,'fingerprint':key,'result':result},on_conflict='user_id,source_id,stage,fingerprint').execute()
            else:
                import time
                with self.connection() as db:
                    db.execute('insert or replace into processing_checkpoints values(?,?,?,?,?,?)',(owner or 'local',source,stage,key,raw,time.time()))
        except Exception:
            from logger import get_logger
            get_logger('execution').warning('Checkpoint save unavailable; completed content is still retained')

    def prune(self):
        cutoff=datetime.now(timezone.utc)-timedelta(days=30)
        if self.cloud:
            self.client.table('processing_checkpoints').delete().lt('created_at',cutoff.isoformat()).execute()
        else:
            with self.connection() as db:
                db.execute('delete from processing_checkpoints where created_at<?',(cutoff.timestamp(),))


def get_store(): return Store()
