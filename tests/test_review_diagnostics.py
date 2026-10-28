import json
import threading
from types import SimpleNamespace

import pytest

from source_coverage import audit_source, SourceReview
from reading_generation import record_review
from focused_editor import _source_groups


def test_keyed_source_receipts_and_patches_are_equivalent_to_lists():
    data={'edits':{'body':{'text':'Corrected claim.','source_ids':['S1']}},
          'additions':{'added:1':{'topic':'Condition','heading':'Limit','text':'Only for adults.','source_ids':['S1']}},
          'coverage':{'S1':{'kind':'content','fields':['body','added:1']}}}
    review=audit_source('Claim applies only to adults.',{'body':'Original claim.'},lambda *_:data,repair=False,best_effort=True)
    assert review.complete
    assert review.fields['body']=='Corrected claim.'
    assert len(review.additions)==1


def test_conflicting_keyed_source_identity_never_verifies_coverage():
    data={'coverage':{'S1':{'unit':'S2','kind':'content','fields':['body']}}}
    review=audit_source('Real source.',{'body':'Claim.'},lambda *_:data,repair=False,best_effort=True)
    assert not review.complete and 'invalid_lists' in review.issues
    assert review.fields['body']=='Claim.'


def test_review_metrics_separate_missing_information_from_unverified_receipts():
    engine=SimpleNamespace(_generation_lock=threading.RLock(),generation_report={})
    review=SourceReview({},[],{},['S1','S2'],{'S2':'PRIVATE ORIGINAL'},['missing_units','PRIVATE PROVIDER MESSAGE'])
    record_review(engine,False,'coverage_gap',review=review)
    result=engine.generation_report['coverage']
    assert result['unverified_units']==2 and result['identified_gap_units']==1
    assert result['issues']=={'missing_units':1}
    assert 'PRIVATE' not in json.dumps(result)


def test_group_boundary_prefers_existing_topic_without_losing_notes():
    rows=[{'topic':t,'text':'word '*100,'id':str(i)} for i,t in enumerate(['A','A','B','B','C'])]
    groups=_source_groups(rows,2,'en')
    assert [r['topic'] for r in groups[0]]==['A','A']
    assert [r for group in groups for r in group]==rows


@pytest.mark.parametrize('video',[True,False])
@pytest.mark.parametrize('status,retries',[(401,False),(403,False),(400,False),(404,False),(429,True),(502,True)])
def test_model_retry_only_repeats_transient_provider_failures(video,status,retries):
    import httpx
    from openai import APIStatusError
    from unittest.mock import Mock
    from tenacity import wait_none
    from note_summarizer import NoteSummarizer
    from summarizer import Summarizer
    engine=(NoteSummarizer if video else Summarizer)(api_key='fixture')
    response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='Available notes.'))])
    failure=APIStatusError('synthetic',response=httpx.Response(status,request=httpx.Request('POST','https://example.com')),body={})
    request=Mock(side_effect=[failure,response])
    engine.client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request)))
    method=(engine._call_llm if video else engine._call_llm_with_retry).__wrapped__.retry_with(wait=wait_none())
    args=('system','source') if video else ('source',)
    if retries:method(engine,*args)
    else:
        with pytest.raises(APIStatusError):method(engine,*args)
    assert request.call_count==(2 if retries else 1)


def test_output_limit_and_billing_exhaustion_are_not_retried_unchanged():
    import httpx
    from openai import APIStatusError
    from model_execution import retryable_model_failure
    from summary_errors import SummaryOutputError
    assert not retryable_model_failure(SummaryOutputError('length'))
    assert not retryable_model_failure(SummaryOutputError('content_filter'))
    quota=APIStatusError('synthetic',response=httpx.Response(429,request=httpx.Request('POST','https://example.com')),body={'code':'insufficient_quota'})
    assert not retryable_model_failure(quota)


@pytest.mark.parametrize('fails',[False,True])
def test_video_overview_has_its_own_budget_and_failure_measurement(fails):
    from unittest.mock import patch
    from note_summarizer import NoteSummarizer
    from reading_budget import PLAN,make_plan
    engine=NoteSummarizer(api_key='fixture');engine.generation_report={}
    token=PLAN.set(make_plan('English source '*20000,133*60,'en'))
    def respond(system,payload,timeout):
        assert 'approximately 250 words' in system
        assert timeout==30
        if fails:raise TimeoutError('private provider details')
        return {'overview':'Central claim with its condition.'}
    try:
        with patch.object(engine,'_editorial_json',side_effect=respond) as call:
            result=engine._merge_chunk_notes('Title',['## Argument\n\nExact condition.\n\n## AI Summary\n\nCentral claim.'],False,whole_summary=True)
        assert call.call_count==1 and 'Exact condition.' in result
        metrics=engine.generation_report['overview']
        assert metrics['status']==('retained_source_indexes' if fails else 'generated')
        if fails:assert metrics['reason']=='timeout'
        assert 'private' not in json.dumps(metrics)
    finally:PLAN.reset(token)
