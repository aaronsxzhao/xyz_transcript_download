import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import BadRequestError, InternalServerError

from json_model_stream import collect_completion
from processing_execution import Execution, bind
from reading_editor import _call_editor, call_editor
from scripts.validate_authorized_episode import Calls, MemoryCheckpoints, TrackedClient
from summary_errors import ProcessingCancelledError, SummaryOutputError


def event(text=None,finish=None,usage=None):
    return NS(choices=[NS(delta=NS(content=text,refusal=None),finish_reason=finish)],usage=usage,model='synthetic')


class Stream:
    def __init__(self,events):self.events=events;self.closed=0
    def __iter__(self):
        for value in self.events:
            if callable(value):value=value()
            if isinstance(value,BaseException):raise value
            yield value
    def close(self):self.closed+=1


def client_for(stream):
    client=Mock(base_url='https://synthetic.example/v1');client.with_options.return_value=client
    client.chat.completions.create.return_value=stream
    return client


def test_streamed_json_is_private_until_clean_stop_and_usage_only_event_is_allowed():
    stream=Stream([event('{"ok":'),NS(choices=[],usage=None,model='synthetic'),event('true}',finish='stop')])
    raw=client_for(stream)
    assert _call_editor(raw,'synthetic','Instruction',json.dumps({'mode':'single'}),10)=={'ok':True}
    assert raw.chat.completions.create.call_args.kwargs['stream'] is True
    assert stream.closed==1


@pytest.mark.parametrize('finish',[None,'length','content_filter'])
def test_valid_json_does_not_make_an_unfinished_or_rejected_stream_pass(finish):
    stream=Stream([event('{"ok":true}',finish)])
    with pytest.raises(SummaryOutputError):_call_editor(client_for(stream),'test','Instruction','{"mode":"single"}',10)
    assert stream.closed==1


def test_stream_failure_and_cancellation_close_connection_without_checkpointing_partial_json():
    for error in (httpx.ReadTimeout('synthetic'),ProcessingCancelledError('cancel')):
        stream=Stream([event('{"private":'),error]);store=MemoryCheckpoints()
        with bind(Execution('owner','source',store)),pytest.raises(type(error)):
            call_editor(client_for(stream),'test','Instruction','{"mode":"single"}',10)
        assert stream.closed==1 and store.values=={}


def test_cancellation_is_checked_between_stream_events():
    execution=Execution('owner','source',MemoryCheckpoints())
    def cancel():execution.cancelled=True;return event('true}',finish='stop')
    stream=Stream([event('{"ok":'),cancel])
    with bind(execution),pytest.raises(ProcessingCancelledError):collect_completion(stream)
    assert stream.closed==1


def test_ignored_stream_flag_consumes_one_normal_json_response_without_second_request():
    body={'model':'synthetic','choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
    stream=Stream([]);stream.response=httpx.Response(200,headers={'content-type':'application/json'},json=body)
    raw=client_for(stream)
    assert _call_editor(raw,'test','Instruction','{"mode":"single"}',10)=={'ok':True}
    assert raw.chat.completions.create.call_count==1 and raw._json_stream_disabled is True
    assert stream.closed==1


@pytest.mark.parametrize('param,retry',[('stream',True),('response_format',False),('model',False)])
def test_only_explicit_stream_parameter_rejection_allows_nonstream_compatibility_fallback(param,retry):
    error=BadRequestError('synthetic',response=httpx.Response(400,request=httpx.Request('POST','https://synthetic.example/v1')),
        body={'param':param,'code':'unsupported_parameter'})
    valid=NS(choices=[NS(finish_reason='stop',message=NS(content='{"ok":true}'))])
    raw=client_for(None);raw.chat.completions.create.side_effect=[error,valid]
    if retry:
        assert _call_editor(raw,'test','Instruction','{"mode":"single"}',10)=={'ok':True}
        assert raw.chat.completions.create.call_count==2
        assert 'stream' not in raw.chat.completions.create.call_args.kwargs
        assert raw._json_stream_disabled is True
    else:
        with pytest.raises(BadRequestError):_call_editor(raw,'test','Instruction','{"mode":"single"}',10)
        assert raw.chat.completions.create.call_count==1


def test_stream_accounting_spans_body_consumption_keeps_owner_slot_and_reuses_completed_checkpoint():
    report={};calls=Calls(Mock(),report,Mock(),maximum=1);observer=Mock();calls.observer=observer
    clock=[10.0]
    def during():
        assert calls.active==1
        clock[0]=15.0
        return event('true}',finish='stop')
    usage=NS(prompt_tokens=4,completion_tokens=3,total_tokens=7)
    stream=Stream([event('{"ok":'),during,NS(choices=[],usage=usage,model='synthetic')])
    raw=client_for(stream);tracked=TrackedClient(raw,calls);store=MemoryCheckpoints()
    parameters={'model':'test','messages':[{'role':'user','content':'{"mode":"single"}'}],'stream':True}
    with patch('scripts.validate_authorized_episode.time.monotonic',side_effect=lambda:clock[0]):
        with bind(Execution('owner','source',store)):
            assert call_editor(tracked,'test','Instruction','{"mode":"single"}',10)=={'ok':True}
    assert calls.active==0 and report['peak_model_concurrency']==1
    assert report['model_create_calls']==1 and report['failed_model_create_calls']==0
    assert report['provider_request_seconds_sum']==5.0
    assert report['provider_reported_usage']=={'prompt_tokens':4,'completion_tokens':3,'total_tokens':7}
    assert sum(report['response_model_hash_counts'].values())==1 and observer.observe.call_count==1
    assert stream.closed==1
    resumed=Execution('owner','source',store)
    with bind(resumed):assert call_editor(tracked,'test','Instruction','{"mode":"single"}',10)=={'ok':True}
    assert raw.chat.completions.create.call_count==1 and resumed.hits==1


def test_failed_stream_releases_account_slot_and_marks_incomplete_provider_call():
    report={};calls=Calls(Mock(),report,Mock(),maximum=1)
    stream=Stream([event('{"ok":'),httpx.ReadError('synthetic')]);tracked=TrackedClient(client_for(stream),calls)
    with pytest.raises(httpx.ReadError):_call_editor(tracked,'test','Instruction','{"mode":"single"}',10)
    assert calls.active==0 and report['failed_model_create_calls']==1
    assert report['model_errors_by_phase']['draft']['count']==1
    assert stream.closed==1


@pytest.mark.parametrize('status,retry',[(524,True),(500,True),(429,True),(400,False),(401,False),(403,False)])
def test_draft_transport_retry_is_once_in_place_and_never_retries_auth_or_bad_requests(status,retry):
    from transcript_reading import call_json,source_lines,ReadingProviderError
    _,lines=source_lines('The source includes a necessary condition.')
    payload=json.dumps({'mode':'single','primary_source':[{'id':line.id,'text':line.text} for line in lines]})
    valid={'sections':[{'heading':'Condition','paragraphs':[{'text':'A necessary condition applies.',
        'source_ranges':[{'start':lines[0].id,'end':lines[-1].id}]}]}]}
    from openai import APIStatusError
    error=APIStatusError('synthetic',response=httpx.Response(status,request=httpx.Request('POST','https://synthetic.example/v1')),body={})
    raw=client_for(None);raw.chat.completions.create.side_effect=[error,
        NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps(valid)))])]
    owner=NS(client=raw,model='synthetic',generation_report={})
    if retry:assert call_json(owner,'Instruction',payload,10)==valid
    else:
        with pytest.raises(ReadingProviderError):call_json(owner,'Instruction',payload,10)
    assert raw.chat.completions.create.call_count==(2 if retry else 1)
    assert all(call.kwargs['messages'][1]['content']==payload for call in raw.chat.completions.create.call_args_list)
    assert owner.generation_report.get('draft_transport_retries',0)==int(retry)
    assert owner.generation_report.get('format_retries',0)==0


def test_two_incomplete_streams_exhaust_one_transport_retry_without_format_or_source_restart():
    from transcript_reading import call_json,source_lines
    _,lines=source_lines('The source includes a necessary condition.')
    payload=json.dumps({'mode':'single','primary_source':[{'id':line.id,'text':line.text} for line in lines]})
    streams=[Stream([event('{"sections":[]}')]) for _ in range(2)]
    raw=client_for(None);raw.chat.completions.create.side_effect=streams
    owner=NS(client=raw,model='synthetic',generation_report={})
    with pytest.raises(SummaryOutputError) as error:call_json(owner,'Instruction',payload,10)
    assert error.value.reason=='stream_incomplete'
    assert raw.chat.completions.create.call_count==2 and all(stream.closed==1 for stream in streams)
    assert owner.generation_report['draft_transport_retries']==1
    assert owner.generation_report.get('format_retries',0)==0


def test_content_filter_does_not_trigger_protocol_fallback_even_with_stream_parameter_label():
    error=BadRequestError('synthetic',response=httpx.Response(400,request=httpx.Request('POST','https://synthetic.example/v1')),
        body={'param':'stream','code':'content_filter'})
    raw=client_for(None);raw.chat.completions.create.side_effect=error
    with pytest.raises(BadRequestError):_call_editor(raw,'test','Instruction','{"mode":"single"}',10)
    assert raw.chat.completions.create.call_count==1


def test_streamed_refusal_cannot_be_published_as_valid_json():
    rejected=event('{"ok":true}',finish='stop');rejected.choices[0].delta.refusal='synthetic refusal'
    stream=Stream([rejected]);raw=client_for(stream)
    with pytest.raises(SummaryOutputError) as error:_call_editor(raw,'test','Instruction','{"mode":"single"}',10)
    assert error.value.code=='content_filter' and raw.chat.completions.create.call_count==1
    assert stream.closed==1


def test_guard_is_rechecked_at_actual_http_dispatch_after_model_admission():
    from scripts.validate_authorized_episode import TestGuardStopped
    report={};guard=Mock(side_effect=[None,TestGuardStopped('test_guard')]);calls=Calls(guard,report,Mock(),maximum=1)
    raw=client_for(None)
    raw.chat.completions.create.side_effect=lambda **kwargs:calls.outbound(httpx.Request('POST','https://synthetic.example/v1',json=kwargs))
    with pytest.raises(TestGuardStopped):TrackedClient(raw,calls).chat.completions.create(model='test',messages=[])
    assert calls.http_attempts==0 and calls.active==0 and guard.call_count==2
