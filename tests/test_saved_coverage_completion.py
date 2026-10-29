import re
import json
import time
from unittest.mock import Mock
import pytest
from scripts.complete_saved_coverage import CASES, OWNER_ANCHOR, review_document, remove_audit_notice
from summary_errors import AUDIT_WARNING, FORMAT_WARNING, _EN_NOTICES


def test_fixed_authorized_scope():
    assert OWNER_ANCHOR == 'bc2c988b-2b4'
    assert len(set(CASES)) == 14
    assert sum(kind == 'podcast' for kind, _ in CASES) == 4


def test_only_leading_audit_notice_is_removed():
    body = 'Source passage\n\n' + AUDIT_WARNING
    assert remove_audit_notice(AUDIT_WARNING+'\n\n'+FORMAT_WARNING+'\n\n'+body) == FORMAT_WARNING+'\n\n'+body
    assert remove_audit_notice(_EN_NOTICES['audit']+'\n\nText') == 'Text'


def test_existing_prose_cannot_be_rewritten():
    call = Mock(return_value={'edits':[{'field':'body','text':'New claim','source_ids':['S1']}], 'coverage':[{'unit':'S1','kind':'content','fields':['body']}]})
    result = review_document('Source claim.', {'body':'Original claim.'}, call)
    assert not result['complete']
    assert not result['additions']


def test_missing_receipt_remains_incomplete():
    result = review_document('Source claim.', {'body':'Original claim.'}, Mock(return_value={'coverage':[]}))
    assert not result['complete']
    assert result['checks'][0]['unverified_units'] == 1


def test_quotes_are_not_counted_as_covered_summary():
    def call(system,payload,timeout):
        fields = json.loads(payload)['draft_fields']
        assert 'Secret evidence' not in fields['body']
        return {'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}
    assert review_document('Source claim.', {'body':'Reading text\n\n> Secret evidence'}, call)['complete']


def test_addition_carries_forward_with_valid_unique_field(monkeypatch):
    monkeypatch.setattr('scripts.complete_saved_coverage.passage_index',lambda fields:dict(fields))
    monkeypatch.setattr('source_coverage.split_source',lambda *args:['First claim.', 'Second claim.'])
    calls=[]
    def call(system,payload,timeout):
        request=json.loads(payload); calls.append(request)
        if len(calls)==1:
            return {'additions':[{'id':'added:1','topic':'Claim','heading':'First','text':'First claim.','source_ids':['S1']}], 'coverage':[{'unit':'S1','kind':'content','fields':['added:1']}]}
        assert 'point:4' in request['draft_fields']
        assert request['draft_fields']['point:3'] == 'Existing claim.'
        return {'coverage':[{'unit':'S1','kind':'content','fields':['point:3']}]}
    result=review_document('Both claims.', {'body':'Reading text.','point:3':'Existing claim.'},call)
    assert result['complete'] and len(result['additions'])==1


def test_expired_deadline_does_not_call_provider():
    call=Mock()
    result=review_document('Source claim.',{'body':'Reading text.'},call,deadline=time.monotonic()-1)
    assert not result['complete']
    call.assert_not_called()


def test_long_draft_context_is_bounded_and_relevant():
    from scripts.complete_saved_coverage import relevant_passages
    fields={f'point:{i}':('unrelated advertising slogans. '*70) for i in range(50)}
    fields['point:51']='The investment requires a margin of safety and a competitive advantage.'
    selected=relevant_passages('Margin of safety is necessary for an investment.',fields,40000)
    assert 'point:51' in selected
    assert sum(map(len,selected.values())) <= 40000


def test_addition_checks_unselected_prose_before_being_accepted():
    from scripts.complete_saved_coverage import confirm_missing_addition
    addition={'source_quote':'Real source','text':'A meaningful condition.'}
    fields={'a':'Other context','b':'The meaningful condition.'}
    call=Mock(return_value={'covered':True,'fields':['b']})
    assert not confirm_missing_addition(addition,fields,{'a':'Other context'},call)
    assert json.loads(call.call_args.args[1])['existing_fields']=={'b':fields['b']}
    call=Mock(return_value={'covered':True,'fields':['invented']})
    with pytest.raises(ValueError):
        confirm_missing_addition(addition,fields,{'a':'Other context'},call)


def test_index_keeps_all_prose_even_for_large_fields():
    from scripts.complete_saved_coverage import passage_index
    text='Important condition. '*500
    assert ''.join(passage_index({'body':text}).values()).strip()==text.strip()


def test_duplicate_check_uses_its_own_response_contract(monkeypatch):
    from scripts.complete_saved_coverage import CONTRACT
    monkeypatch.setattr('scripts.complete_saved_coverage.relevant_passages',lambda source,fields: {'body':fields['body']})
    calls=[]
    def call(system,payload,timeout):
        data=json.loads(payload); calls.append(data)
        if 'existing_fields' in data:
            assert CONTRACT not in system
            return {'covered':True,'fields':['other']}
        return {'additions':[{'id':'added:1','topic':'Condition','heading':'Exception','text':'The effect reverses.','source_ids':['S1']}], 'coverage':[{'unit':'S1','kind':'content','fields':['added:1']}]}
    result=review_document('The effect reverses.',{'body':'The general effect.','other':'The effect reverses.'},call)
    assert result['complete'] and not result['additions'] and len(calls)==2


def test_resume_only_calls_unfinished_partition_and_preserves_addition(monkeypatch):
    monkeypatch.setattr('scripts.complete_saved_coverage.passage_index',lambda fields:dict(fields))
    monkeypatch.setattr('source_coverage.split_source',lambda *args:['First claim.','Second claim.'])
    addition={'topic':'First','summary':'First claim.','original_quote':'First claim.','timestamp':''}
    def call(system,payload,timeout):
        request=json.loads(payload)
        assert 'First claim.' not in request['source_units'].values()
        assert 'First claim.' in request['draft_fields'].values()
        return {'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}
    provider=Mock(side_effect=call)
    result=review_document('Both.',{'body':'Second claim.'},provider,resume={'checks':[{'chunk':1,'complete':True}], 'additions':[addition]})
    assert result['complete'] and result['resumed_chunks']==1
    assert result['additions']==[addition] and provider.call_count==1


def test_incomplete_checkpoint_is_not_treated_as_completed():
    provider=Mock(return_value={'coverage':[{'unit':'S1','kind':'content','fields':['body']}]})
    result=review_document('First claim.',{'body':'First claim.'},provider,resume={'checks':[{'chunk':1,'complete':False},{'chunk':999,'complete':True}]})
    assert result['complete'] and result['resumed_chunks']==0 and provider.call_count==1


def test_real_coverage_validator_accepts_partitioned_video_fields():
    fields={'body':'First argument. '*400}
    def call(system,payload,timeout):
        request=json.loads(payload)
        return {'coverage':[{'unit':unit,'kind':'content','fields':list(request['draft_fields'])} for unit in request['source_units']]}
    result=review_document('A substantive source argument.',fields,call)
    assert result['complete']


def test_large_point_field_ids_do_not_collide_with_existing_points():
    from scripts.complete_saved_coverage import passage_index
    fields={'point:1':'Long argument. '*500,'point:2':'Other argument.'}
    indexed=passage_index(fields)
    assert indexed['point:2']=='Other argument.'
    assert all(re.fullmatch(r'point:\d+',key) for key in indexed)
