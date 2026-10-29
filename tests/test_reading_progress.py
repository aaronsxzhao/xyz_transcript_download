from types import SimpleNamespace
from unittest.mock import patch
import pytest
from reading_progress import SummaryProgress, stage
from summary_errors import ProcessingCancelledError


def test_stage_change_is_published_even_without_percentage_change():
    updates=[]
    bridge=SummaryProgress(lambda value,message:updates.append((value,message)),72,94)
    stage(bridge.stage,'inventory',1,2)
    stage(bridge.stage,'coverage',0,8)
    stage(bridge.stage,'repair',0,8)
    stage(bridge.stage,'recheck',0,8)
    assert len(updates)==4
    assert updates[-2][0]==updates[-1][0]
    assert 'Filling missing details' in updates[-2][1]
    assert 'Verifying additions' in updates[-1][1]


def test_review_capacity_change_does_not_regress_progress_or_reach_success():
    updates=[];bridge=SummaryProgress(lambda value,message:updates.append(value),70,95)
    stage(bridge.stage,'grounding',1,1)
    stage(bridge.stage,'grounding',1,20)
    stage(bridge.stage,'render',1,1)
    assert updates==sorted(updates) and max(updates)==95


def test_cancellation_propagates_at_stage_boundaries():
    def cancel():raise ProcessingCancelledError()
    bridge=SummaryProgress(lambda *args:pytest.fail('Cancelled update'),72,94,cancel)
    with pytest.raises(ProcessingCancelledError):stage(bridge.stage,'draft')


@pytest.mark.parametrize('mode',['single','segmented'])
def test_actual_pipeline_reports_generation_review_inventory_and_repair(mode):
    from transcript_reading import generate
    from tests.test_transcript_reading import provider
    from tests.test_coverage_ledger import CASES, scripted
    events=[];calls=[];case=CASES[0]
    engine=SimpleNamespace(generation_mode=mode,chunk_chars=1000,generation_report={})
    with patch('transcript_reading.call_json',side_effect=provider(calls)),patch('coverage_ledger.request',side_effect=scripted(case,[])):
        generate(engine,case['source'],'Title',stage_callback=events.append)
    names=[e['stage'] for e in events]
    for name in ['draft','grounding','inventory','coverage','repair','recheck','render']:
        assert name in names
    assert events[-1]['fraction']==1
    inventory=[e for e in events if e['stage']=='inventory']
    assert inventory[0]['completed']==0 and inventory[-1]['completed']==inventory[-1]['total']
    assert 'full-transcript' in events[0]['message'] if mode=='single' else 'sections' in events[0]['message']
