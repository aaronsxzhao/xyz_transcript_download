import json
from unittest.mock import Mock, patch

import pytest

from reading_budget import PLAN, make_plan, guidance, diagnostics, VERSION
from reading_generation import generation_session
from processing_execution import parallel_map
from reading_editor import edit_sections


def test_repair_budget_counts_existing_note_instead_of_allocating_again():
    from reading_budget import revision_guidance
    token=PLAN.set({'language':'en','target_low':10,'target_high':20,'unit':'English words'})
    try:
        text=revision_guidance([{'paragraphs':[{'text':'word '*25}]}],'Brief overview')
        assert '27 English words' in text and '0 remain' in text
        assert 'not a fresh allowance' in text and 'still preserve missing essential meaning' in text
    finally:PLAN.reset(token)


@pytest.mark.parametrize('language,minutes,expected',[
    ('en',14,(600,800)), ('zh',67,(3000,3500)), ('en',133,(3000,4000)),
])
def test_agreed_reading_targets(language,minutes,expected):
    source='原文内容。'*6000 if language=='zh' else 'source evidence '*20000
    plan=make_plan(source,minutes*60,language)
    assert (plan['target_low'],plan['target_high'])==expected
    assert plan['estimated_duration'] is False


def test_sparse_or_invalid_source_never_invites_padding():
    sparse=make_plan('A short source.',133*60,'en')
    assert sparse['target_high']<=3
    for duration in [0,None,'bad',float('nan'),float('inf'),-1]:
        assert make_plan('word '*1400,duration,'en')['estimated_duration']
    assert 'target_high' not in make_plan('bonjour',100,'fr')


def test_parallel_chunks_share_one_budget_and_reset_after_failure():
    class Engine:
        model='synthetic'
        @generation_session
        def generate(self,transcript_text,duration):
            assert PLAN.get()['target_high']==4000
            prompts=parallel_map(guidance,[transcript_text[:len(transcript_text)//2]]*2)
            assert all('1500-2000' in prompt for prompt in prompts)
            raise RuntimeError('cancel')
    with pytest.raises(RuntimeError):Engine().generate('English source evidence. '*2000,133*60)
    assert PLAN.get() is None


def test_metrics_are_advisory_without_source_or_private_values():
    plan=make_plan('English source evidence. '*1000,14*60,'en')
    text='# A heading\n\n[Heading](#heading)\n\nA useful conclusion.\n\n> private original quotation\n\n![chart](https://secret.example/image)'
    report=diagnostics(text,'private source',plan)
    assert report['budget_status']=='below' and report['advisory_only']
    assert report['output_words']==5  # heading + prose, not TOC/quote/image
    assert 'private' not in json.dumps(report) and 'secret.example' not in json.dumps(report)


def test_over_budget_valid_edit_is_retained_and_media_stays_in_order():
    rows=[{'id':'N1','topic':'Argument','text':'First. Screenshot-[01:00]'},
          {'id':'N2','topic':'Argument','text':'Condition. Screenshot-[02:00]'}]
    rewritten=('A grounded explanation. '*300)+'Screenshot-[01:00]\nScreenshot-[02:00]'
    call=Mock(side_effect=[{'groups':[{'title':'Argument','ids':['N1','N2']}]},
        {'paragraphs':[{'heading':'Conditions','text':rewritten,'ids':['N1','N2'],'evidence_id':'N1'}]},
        {'complete':True,'grounded':True}])
    token=PLAN.set(make_plan('English evidence. '*100,60,'en'))
    try:
        result=edit_sections(rows,call,preserve_order=True)
        assert rewritten in result[0]['text']
        assert 'SOFT READING BUDGET' in call.call_args_list[1].args[0]
    finally:PLAN.reset(token)


def test_measurement_failure_never_discards_summary():
    class Engine:
        model='synthetic'
        @generation_session
        def generate(self,transcript_text):return 'Usable summary'
    engine=Engine()
    with patch('reading_budget.diagnostics',side_effect=ValueError('bad telemetry')):
        assert engine.generate('English source')=='Usable summary'
    assert engine.generation_report['prompt_version']==VERSION
    assert engine.generation_report['reading']['measurement_failed']


def test_minimal_is_shorter_than_detailed_without_changing_fidelity():
    source='English source evidence. '*10000
    detailed=make_plan(source,133*60,'en','detailed')
    minimal=make_plan(source,133*60,'en','minimal')
    assert detailed['target_low']==3000 and detailed['target_high']==4000
    assert minimal['target_low']==1950 and minimal['target_high']==2800
    assert make_plan(source,133*60,'en','tutorial')['target_high']==4000
    token=PLAN.set(minimal)
    try: assert 'drop an essential condition' in guidance(source)
    finally: PLAN.reset(token)
