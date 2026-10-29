import json
from unittest.mock import Mock
import pytest
from source_coverage import audit_source, source_units
from summary_errors import ProcessingCancelledError


def test_all_missing_receipts_are_completed_not_only_two_exclusions():
    source = 'Argument and condition. ' * 170
    units = source_units(source)
    assert len(units) > 2
    def complete(system, payload, timeout):
        request = json.loads(payload)
        assert set(request['receipt_units_to_recheck']) == set(units)
        return {'coverage':[{'unit':key,'kind':'content','fields':['body']} for key in units]}
    repair = Mock(side_effect=complete)
    result = audit_source(source, {'body':'The argument and its condition.'}, Mock(return_value={'coverage':[]}), best_effort=True, recheck=repair)
    assert result.complete and repair.call_count == 1
    assert result.receipt_recheck['resolved'] == len(units)


def test_actual_gap_gets_a_grounded_delta_instead_of_a_fake_receipt():
    first = {'coverage':[{'unit':'S1','kind':'missing'}]}
    correction = {'additions':[{'id':'added:1','topic':'Conditions','heading':'Exception','text':'The effect reverses in low temperatures.','source_ids':['S1']}],
                  'coverage':[{'unit':'S1','kind':'content','fields':['body','added:1']}]}
    result = audit_source('The effect reverses in low temperatures.', {'body':'The general effect.'}, Mock(return_value=first), best_effort=True, recheck=Mock(return_value=correction))
    assert result.complete and len(result.additions) == 1
    assert 'low temperatures' in result.fields['added:1']


def test_second_pass_preserves_first_pass_fixes_and_only_checks_remainder():
    source = 'Condition. ' * 180
    units = list(source_units(source))
    calls = []
    def repair(system, payload, timeout):
        pending = json.loads(payload)['receipt_units_to_recheck']; calls.append(pending)
        picked = pending[:1] if len(calls) == 1 else pending
        return {'coverage':[{'unit':key,'kind':'content','fields':['body']} for key in picked]}
    result = audit_source(source, {'body':'Conditional argument.'}, Mock(return_value={'coverage':[]}), best_effort=True, recheck=repair)
    assert result.complete and len(calls) == 2
    assert set(calls[1]) == set(units) - {calls[0][0]}
    assert result.receipt_recheck['resolved'] == len(units)


@pytest.mark.parametrize('failure',[TimeoutError(),json.JSONDecodeError('invalid','x',0)])
def test_initial_review_failure_gets_one_bounded_saved_provider_retry(failure):
    retry = Mock(return_value={'coverage':[{'unit':'S1','kind':'content','fields':['body']}]})
    result = audit_source('An argument.', {'body':'An argument.'}, Mock(side_effect=failure), best_effort=True, recheck=retry)
    assert result.complete and retry.call_count == 1
    assert retry.call_args.args[2] == 60


def test_cancellation_is_never_retried():
    retry = Mock()
    with pytest.raises(ProcessingCancelledError):
        audit_source('Source.', {'body':'Draft.'}, Mock(side_effect=ProcessingCancelledError()), best_effort=True, recheck=retry)
    retry.assert_not_called()


def test_unavailable_completion_stops_and_records_reason_without_marking_covered():
    retry = Mock(side_effect=TimeoutError())
    result = audit_source('Source.', {'body':'Draft.'}, Mock(return_value={'coverage':[]}), best_effort=True, recheck=retry)
    assert not result.complete and retry.call_count == 2
    assert result.receipt_recheck['calls'] == 2
    assert result.receipt_recheck['failure_reason'] == 'timeout'


def test_invalid_envelope_recovery_keeps_independently_accepted_edit():
    first = {'edits':[{'field':'body','text':'Corrected condition.','source_ids':['S1']}], 'coverage':'invalid'}
    def retry(system,payload,timeout):
        assert json.loads(payload)['draft_fields']['body'] == 'Corrected condition.'
        return {'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}
    result = audit_source('Corrected condition.', {'body':'Old draft.'}, Mock(return_value=first), best_effort=True, recheck=retry)
    assert result.complete and result.fields['body'] == 'Corrected condition.'


def test_envelope_recovery_timeout_keeps_valid_earlier_correction():
    first = {'edits':[{'field':'body','text':'Corrected condition.','source_ids':['S1']}], 'coverage':'invalid'}
    result = audit_source('Corrected condition.', {'body':'Old draft.'}, Mock(return_value=first), best_effort=True, recheck=Mock(side_effect=TimeoutError()))
    assert not result.complete and result.fields['body'] == 'Corrected condition.'
    assert result.receipt_recheck['failure_reason'] == 'timeout'


def test_auth_failure_does_not_trigger_repeated_completion_calls():
    class AuthFailure(Exception):
        status_code = 401
    retry = Mock(side_effect=AuthFailure())
    result = audit_source('Source.', {'body':'Draft.'}, Mock(return_value={'coverage':[]}), best_effort=True, recheck=retry)
    assert not result.complete and retry.call_count == 1
    assert result.receipt_recheck['failure_reason'] == 'provider_configuration'


def test_completion_additions_cannot_overwrite_verified_fields_or_use_outside_units():
    response = {'additions':[{'id':'body','topic':'Topic','heading':'Overwrite','text':'Changed','source_ids':['S1']},
        {'id':'added:2','topic':'Topic','heading':'Outside','text':'Changed','source_ids':['S99']}],
        'coverage':[{'unit':'S1','kind':'content','fields':['added:2']}]}
    result = audit_source('Source.', {'body':'Original draft.'}, Mock(return_value={'coverage':[]}), best_effort=True, recheck=Mock(return_value=response))
    assert not result.complete and result.fields == {'body':'Original draft.'}
    assert not result.additions
