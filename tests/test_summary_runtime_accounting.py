from unittest.mock import Mock, patch

import pytest

from processing_execution import Execution
from reading_budget import PLAN, estimated_minutes, make_plan, visible_prose
from focused_editor import edit_whole_note


def test_failed_provider_work_is_measured_but_never_checkpointed():
    store=Mock();store.get_checkpoint.return_value=None
    execution=Execution('owner','source',store)
    with patch('processing_execution.time.monotonic',side_effect=[10,15]):
        with pytest.raises(TimeoutError):
            execution.cached('model','key',Mock(side_effect=TimeoutError()))
    assert execution.metrics['model']=={'seconds':5,'calls':1,'failed_calls':1}
    store.put_checkpoint.assert_not_called()


def test_cached_work_does_not_count_as_a_new_model_call():
    store=Mock();store.get_checkpoint.return_value={'complete':True}
    execution=Execution('owner','source',store);call=Mock()
    assert execution.cached('model','key',call)=={'complete':True}
    assert execution.hits==1 and not execution.metrics
    call.assert_not_called()


@pytest.mark.parametrize('status',[401,403,404])
def test_terminal_provider_error_stops_later_editor_batches_and_keeps_notes(status):
    class Failure(Exception):
        status_code=status
    rows=[{'id':f'N{i}','topic':f'Topic {i}','text':'Evidence '*80} for i in range(30)]
    call=Mock(side_effect=Failure());report={}
    token=PLAN.set(make_plan('English source '*30000,133*60,'en'))
    try:
        result=edit_whole_note(rows,call,report=report)
    finally:PLAN.reset(token)
    assert len(report['batches'])>2
    # Only work already in flight may finish after the first failure.
    assert call.call_count<=2
    assert [row['text'] for row in result]==[row['text'] for row in rows]


def test_personal_reading_rate_is_independent_of_length_target_and_quotes():
    prose=visible_prose('读'*3346+'\n\n> '+'引'*10000)
    assert estimated_minutes(prose,han_per_minute=100000/120)==4.02
    assert estimated_minutes(prose)==9.56
    assert make_plan('读'*20000,67*60,'zh')['target_high']==3500


@pytest.mark.parametrize('rate',[0,-1,float('inf'),float('nan'),True,'833'])
def test_invalid_personal_reading_rates_are_rejected(rate):
    with pytest.raises(ValueError):estimated_minutes('Text',han_per_minute=rate)
