from unittest.mock import Mock, patch
from summarizer import Summarizer, Summary, KeyPoint
from summary_errors import delivery_notice
from podcast_order import chronological_points


def test_one_raw_section_does_not_skip_other_successful_sections():
    engine=Summarizer(api_key='fixture');engine.generation_report={}
    before=KeyPoint('Argument','Already extracted argument','Exact evidence','00:10')
    raw=KeyPoint('Part 2/3: Original transcript','Unedited raw source','','')
    after=KeyPoint('Later','Another extracted argument','Other evidence','01:00')
    summary=Summary('e','Title',delivery_notice('Overview','generation','English'),[before,raw,after],[],[])
    def edit(items,*args,**kwargs):
        assert all('raw source' not in row['text'] for row in items)
        return [dict(row,ids=[row['id']],evidence_id=row['id'],text='Edited '+row['text']) for row in items]
    with patch('reading_editor.edit_sections',side_effect=edit) as call:
        result=engine._edit_reading(summary)
    assert call.call_count==2
    assert result.key_points[1] is raw
    assert result.overview==summary.overview
    assert result.key_points[0].original_quote=='Exact evidence'
    assert result.key_points[2].summary.startswith('Edited')
    assert engine.generation_report['editor']['protected_sections']==1


def test_chapter_ordering_keeps_unknown_times_and_quotes_attached():
    a=KeyPoint('Management','Later','Later evidence','00:57:32')
    unknown=KeyPoint('Management','No time','Untimed evidence','')
    b=KeyPoint('Management','Earlier','Earlier evidence','00:56:31')
    c=KeyPoint('Other','Different chapter','Quote','00:10:00')
    assert chronological_points([a,unknown,b,c])==[b,a,unknown,c]
    assert a.timestamp=='00:57:32' and a.original_quote=='Later evidence'


def test_partial_runs_share_one_budget_and_restore_the_generation_context():
    from reading_budget import PLAN
    engine=Summarizer(api_key='fixture');engine.generation_report={}
    points=[KeyPoint('A','word '*200,'',''),KeyPoint('Original transcript','raw '*100,'',''),KeyPoint('B','word '*200,'','')]
    summary=Summary('e','Title',delivery_notice('Overview','generation','English'),points,[],[])
    plan={'language':'en','target_low':400,'target_high':600}
    observed=[]
    def edit(items,*args,**kwargs):
        observed.append(PLAN.get()['target_high'])
        return [dict(row,ids=[row['id']],evidence_id=row['id']) for row in items]
    token=PLAN.set(plan)
    try:
        with patch('reading_editor.edit_sections',side_effect=edit):
            engine._edit_reading(summary)
        assert len(observed)==2 and all(value<350 for value in observed)
        assert PLAN.get() is plan
    finally:
        PLAN.reset(token)


def test_large_raw_fallback_does_not_starve_successful_notes_of_editing_budget():
    from reading_budget import PLAN
    engine=Summarizer(api_key='fixture');engine.generation_report={}
    raw=KeyPoint('Original transcript','raw '*5000,'','')
    summary=Summary('e','Title',delivery_notice('Overview','generation','English'),
                    [KeyPoint('A','word '*200,'',''),raw,KeyPoint('B','word '*200,'','')],[],[])
    observed=[]
    def edit(items,*args,**kwargs):
        observed.append(PLAN.get()['target_high'])
        return [dict(row,ids=[row['id']],evidence_id=row['id']) for row in items]
    token=PLAN.set({'language':'en','target_low':400,'target_high':600})
    try:
        with patch('reading_editor.edit_sections',side_effect=edit):
            result=engine._edit_reading(summary)
        assert all(200 <= target <= 350 for target in observed)
        assert result.key_points[1] is raw
        assert engine.generation_report['editor']['budget_excludes_protected_source']
    finally:
        PLAN.reset(token)


def test_failed_partial_run_does_not_contaminate_next_successful_report():
    engine=Summarizer(api_key='fixture');engine.generation_report={}
    summary=Summary('e','Title','Overview',[KeyPoint('A','First','',''),
        KeyPoint('Original transcript','Raw','',''),KeyPoint('B','Last','','')],[],[])
    def edit(items,*args,**kwargs):
        report=kwargs['report']
        report['model_calls']=1
        if items[0]['topic']=='A':
            report['retention_reasons']={'timeout':1}
            raise TimeoutError()
        assert 'retention_reasons' not in report and 'fallback_reason' not in report
        return [dict(row,ids=[row['id']],evidence_id=row['id']) for row in items]
    with patch('reading_editor.edit_sections',side_effect=edit):
        engine._edit_reading(summary)
    report=engine.generation_report['editor']
    assert report['runs'][0]['fallback_reason']=='TimeoutError'
    assert 'fallback_reason' not in report['runs'][1]
    assert report['model_calls']==2
