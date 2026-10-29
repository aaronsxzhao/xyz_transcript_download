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
