"""Account-scoped, request-fingerprinted durable work and phase measurements."""
import contextvars
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from functools import wraps

CURRENT = contextvars.ContextVar('processing_execution',default=None)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


class ProcessingPaused(BaseException):
    """Deployment pause at a successfully saved boundary, not user cancellation."""


class Execution:
    def __init__(self,owner,source,store,*,queue_id=None,lease_owner=None):
        self.owner=owner;self.source=source;self.store=store
        self.queue_id=queue_id;self.lease_owner=lease_owner
        self.lock=threading.RLock();self.metrics={};self.hits=0
        self.started=time.monotonic();self.previous_wall=0
        self.cancelled=False;self.pause_requested=False;self.lease_lost=False;self.deleted=False

    def check(self,boundary=False):
        from summary_errors import ProcessingCancelledError
        if self.lease_lost: raise ProcessingPaused()
        if self.cancelled: raise ProcessingCancelledError('Cancelled')
        if boundary and self.pause_requested: raise ProcessingPaused()

    def cached(self,stage,key,call,encode=lambda value:value,decode=lambda value:value):
        self.check()
        started=time.monotonic()
        payload=self.store.get_checkpoint(self.owner,self.source,stage,key)
        if payload is not None:
            try: value=decode(payload)
            except (ValueError,TypeError,KeyError): pass
            else:
                with self.lock: self.hits+=1
                self.check(boundary=True)
                return value
        value=call()
        self.check()
        if value is not None:
            try: payload=encode(value)
            except (ValueError,TypeError,KeyError): payload=None
            if payload is not None: self.store.put_checkpoint(self.owner,self.source,stage,key,payload)
        with self.lock:
            row=self.metrics.setdefault(stage,{'seconds':0,'calls':0})
            row['seconds']+=round(time.monotonic()-started,3);row['calls']+=1
        self.check(boundary=True)
        return value

    def snapshot(self):
        with self.lock: return {'stages':{k:dict(v) for k,v in self.metrics.items()},'checkpoint_hits':self.hits,'wall_seconds':round(self.previous_wall+time.monotonic()-self.started,3)}


@contextmanager
def bind(execution):
    token=CURRENT.set(execution)
    try: yield execution
    finally: CURRENT.reset(token)


def checkpoint_call(stage,identity,call,encode=lambda value:value,decode=lambda value:value):
    execution=CURRENT.get()
    if execution is None: return call()
    return execution.cached(stage,fingerprint(identity),call,encode,decode)


def model_checkpoint(stage):
    """Cache actual completed provider responses, never partial streaming text."""
    def decorate(method):
        @wraps(method)
        def wrapped(self,*args,**kwargs):
            from inspect import signature
            values=signature(method).bind(self,*args,**kwargs)
            values.apply_defaults()
            values={k:v for k,v in values.arguments.items() if k not in ('self','progress_callback')}
            identity={'request':values,'model':self.model,'endpoint':self.base_url,
                      'options':getattr(self,'model_options',{}),'version':2}
            if stage.startswith('podcast'):
                from types import SimpleNamespace
                def encode(value):
                    from summary_format import extract_model_json
                    extract_model_json(value.choices[0].message.content or '')
                    return {'content':value.choices[0].message.content}
                return checkpoint_call(stage,identity,lambda:method(self,*args,**kwargs),
                    encode,lambda payload:SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload['content']),finish_reason='stop')]))
            def encode(value):
                if values.get('json_output'):
                    from summary_format import extract_model_json
                    extract_model_json(value)
                return value
            return checkpoint_call(stage,identity,lambda:method(self,*args,**kwargs),encode)
        return wrapped
    return decorate


def file_fingerprint(path):
    value=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): value.update(chunk)
    return value.hexdigest()


def parallel_map(function,items,workers=2):
    """Bounded independent work; preserve source order and cancellation context."""
    from concurrent.futures import ThreadPoolExecutor
    pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='source_segment')
    futures=[]
    try:
        for item in items:
            context=contextvars.copy_context()
            futures.append(pool.submit(context.run,function,item))
        return [future.result() for future in futures]
    finally:
        for future in futures: future.cancel()
        pool.shutdown(wait=True,cancel_futures=True)


def assert_lease():
    """Fence source/final writes when cancellation or another worker took over."""
    execution = CURRENT.get()
    if execution is None:
        return
    execution.check()
    if execution.queue_id:
        row = execution.store.heartbeat(execution.queue_id, execution.lease_owner, execution.snapshot())
        if row is None:
            raise ProcessingPaused()
        if row.get('cancel_requested'):
            execution.cancelled = True
            execution.check()
