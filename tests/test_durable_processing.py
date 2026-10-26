"""Behavioral tests for interrupted/reclaimed work, checkpoints and model options."""
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from execution_store import Store
from processing_execution import Execution, ProcessingPaused, bind, checkpoint_call, parallel_map, assert_lease
from model_execution import configure, request_options, capabilities


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'work.sqlite')


def enqueue(store,owner='alice',task='one',payload=None):
    return store.enqueue(owner,'podcast',task,'source',payload or {'episode_url':'https://example.org/one'})


def test_simultaneous_admission_creates_only_one_attempt(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(lambda _:enqueue(store),range(8)))
    assert len(set(ids))==1
    assert store.claim('worker')['id']==ids[0]
    assert store.claim('other') is None


def test_expired_lease_is_reclaimed_and_old_worker_cannot_commit(store):
    ident=enqueue(store)
    store.claim('old')
    with store.connection() as db: db.execute('update processing_work set lease_until=0 where id=?',(ident,))
    row=store.claim('new')
    assert row['attempts']==2
    assert store.heartbeat(ident,'old',{}) is None
    assert not store.finish(ident,'old','completed',{})
    execution=Execution('alice','source',store,queue_id=ident,lease_owner='old')
    with bind(execution),pytest.raises(ProcessingPaused): assert_lease()
    assert store.finish(ident,'new','completed',{})


def test_repeated_process_deaths_stop_automatic_retries(store):
    ident=enqueue(store)
    for count in range(3):
        row=store.claim(str(count));assert row['state']=='running'
        with store.connection() as db: db.execute('update processing_work set lease_until=0 where id=?',(ident,))
    assert store.claim('fourth')['state']=='failed'
    assert store.claim('fifth') is None


def test_cancellation_is_owned_and_persisted(store):
    ident=enqueue(store)
    store.cancel('bob','podcast','one')
    assert store.latest('alice','podcast','one')['state']=='queued'
    store.claim('worker')
    store.cancel('alice','podcast','one',deleted=True)
    row=store.heartbeat(ident,'worker',{})
    assert row['cancel_requested'] and row['payload']['deleted']


def test_completed_segment_survives_pause_and_new_execution(store):
    first=Execution('alice','source',store)
    first.pause_requested=True
    generate=Mock(return_value={'text':'complete source section'})
    with bind(first),pytest.raises(ProcessingPaused):
        checkpoint_call('summary',{'model':'one'},generate)
    with bind(Execution('alice','source',store)):
        assert checkpoint_call('summary',{'model':'one'},generate)['text']=='complete source section'
    assert generate.call_count==1
    with bind(Execution('alice','source',store)):
        checkpoint_call('summary',{'model':'changed'},generate)
    with bind(Execution('bob','source',store)):
        checkpoint_call('summary',{'model':'one'},generate)
    assert generate.call_count==3


def test_failed_responses_are_not_checkpointed(store):
    call=Mock(side_effect=[RuntimeError('temporary'),{'text':'fixed'}])
    with bind(Execution('alice','source',store)):
        with pytest.raises(RuntimeError): checkpoint_call('summary','one',call)
        assert checkpoint_call('summary','one',call)=={'text':'fixed'}
    assert call.call_count==2


def test_parallel_segments_retain_context_and_source_order(store):
    barrier=threading.Barrier(2)
    def one(index):
        barrier.wait(timeout=3)
        return checkpoint_call('segment',index,lambda:index)
    execution=Execution('alice','source',store)
    with bind(execution): assert parallel_map(one,[0,1])==[0,1]
    with bind(Execution('alice','source',store)):
        assert checkpoint_call('segment',0,lambda:99)==0


def test_selected_model_options_reach_editor_clones_and_override_legacy_defaults():
    raw=Mock();raw.with_options.return_value=raw
    client=configure(raw,{'reasoning_effort':'high','service_tier':'priority'})
    client.with_options(timeout=10).chat.completions.create(model='selected',reasoning_effort='low')
    assert raw.chat.completions.create.call_args.kwargs=={'model':'selected','reasoning_effort':'high','service_tier':'priority'}


def test_provider_defaults_send_no_options_and_known_model_rejects_bad_value():
    assert request_options({},'https://api.groq.com/openai/v1','openai/gpt-oss-120b')=={}
    from api.custom_models import ModelConfigurationError
    with pytest.raises(ModelConfigurationError):
        request_options({'llm_reasoning_effort':'xhigh'},'https://api.groq.com/openai/v1','openai/gpt-oss-120b')
    assert not capabilities('https://custom.example/v1','gpt-6.1-sol')['known']


def test_drain_blocks_old_embedded_workers_but_not_new_or_external(store):
    import time
    enqueue(store)
    with store.connection() as db:
        db.execute('insert into processing_controls values(?,?,?)',('drain_embedded','new',time.time()+30))
    assert store.claim('old','embedded','old') is None
    assert store.claim('new','embedded','new') is not None
    enqueue(store,task='two')
    assert store.claim('external','worker','old') is not None


def test_source_order_and_timestamps_survive_parallel_audio_completion(store,tmp_path,monkeypatch):
    from transcriber import APITranscriber, Transcript, TranscriptSegment
    audio=tmp_path/'input.mp3';audio.write_bytes(b'audio')
    api=APITranscriber.__new__(APITranscriber);api.max_size=10;api.last_error=''
    api._get_audio_duration=lambda path:1200 if path==audio else 600
    def extract(source,target,start,duration,cancel_check):target.write_bytes(b'chunk');return True
    api._extract_chunk=extract
    barrier=threading.Barrier(2)
    def transcribe(path,eid,language,callback):
        index=int(eid.rsplit('_',1)[1]);barrier.wait(timeout=3)
        return Transcript(eid,'en',600,str(index),[TranscriptSegment(5,10,str(index))])
    api._transcribe_file=transcribe
    with bind(Execution('alice','source',store)):
        result=api._transcribe_large_file(audio,'episode','')
    assert result.text=='0 1'
    assert [segment.start for segment in result.segments]==[5,605]


def test_streamed_podcast_result_is_checkpointed_without_sdk_only_methods(store):
    from processing_execution import model_checkpoint
    class Provider:
        model='selected';base_url='https://example.org/v1';calls=0
        @model_checkpoint('podcast.model')
        def generate(self,prompt,progress_callback=None):
            self.calls+=1
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"overview":"source"}'))])
    provider=Provider()
    with bind(Execution('alice','source',store)):
        first=provider.generate('same',lambda _:None)
    with bind(Execution('alice','source',store)):
        second=provider.generate('same',lambda _:None)
    assert first.choices[0].message.content==second.choices[0].message.content
    assert provider.calls==1


def test_planned_deploy_pauses_do_not_consume_crash_budget(store):
    ident=enqueue(store)
    for _ in range(5):
        assert store.claim('worker')['state']=='running'
        assert store.finish(ident,'worker','queued',{})
    assert store.latest('alice','podcast','one')['attempts']==0


def test_pause_concurrent_with_cancel_cannot_resurrect_queue(store):
    ident=enqueue(store);store.claim('worker')
    store.cancel('alice','podcast','one')
    assert store.finish(ident,'worker','queued',{})
    assert store.latest('alice','podcast','one')['state']=='cancelled'
    assert store.claim('new') is None


def test_worker_completes_persisted_job_and_preserves_checkpoint_on_pause(store,monkeypatch):
    from api.worker import Worker
    from api.routers import processing
    from api.schemas import ProcessingStatus
    ident=enqueue(store,payload={'episode_url':'https://example.org/one','user_id':'alice'})
    job=ProcessingStatus(job_id='one',user_id='alice',status='pending')
    monkeypatch.setattr(processing,'jobs',{'one':job})
    calls=[]
    def process(*args,**kwargs):
        checkpoint_call('test','one',lambda:calls.append(1) or {'complete':True})
        job.status='completed'
    monkeypatch.setattr(processing,'process_episode_sync',process)
    worker=Worker(store=store)
    row=store.claim(worker.ident)
    execution=Execution('alice','source',store,queue_id=ident,lease_owner=worker.ident)
    execution.pause_requested=True
    worker.run(row,execution)
    assert store.latest('alice','podcast','one')['state']=='queued'
    row=store.claim(worker.ident)
    worker.run(row,Execution('alice','source',store,queue_id=ident,lease_owner=worker.ident))
    assert store.latest('alice','podcast','one')['state']=='completed'
    assert calls==[1]
    worker.stop()


def test_summary_settings_resolve_options_without_changing_credentials(monkeypatch):
    from api import llm_settings
    monkeypatch.setattr(llm_settings,'GROQ_API_KEY','test-key')
    result=llm_settings.resolve_llm_settings({'llm_provider':'groq','llm_model':'openai/gpt-oss-120b','llm_reasoning_effort':'low','llm_service_tier':'performance'})
    assert result['api_key']=='test-key'
    assert result['model_options']=={'reasoning_effort':'low','service_tier':'performance'}


def test_official_reasoning_models_omit_unsupported_temperature_without_assuming_gateway_behavior():
    raw=Mock();raw.base_url='https://api.openai.com/v1'
    configure(raw,{}).chat.completions.create(model='gpt-5',temperature=0)
    assert raw.chat.completions.create.call_args.kwargs=={'model':'gpt-5'}
    raw.base_url='https://gateway.example/v1'
    configure(raw,{'reasoning_effort':'high'}).chat.completions.create(model='gpt-5',temperature=0)
    assert raw.chat.completions.create.call_args.kwargs['temperature']==0
