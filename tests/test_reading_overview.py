import json
from unittest.mock import Mock

from reading_overview import compose_overview
from note_summarizer import NoteSummarizer


def test_final_overview_repairs_only_supported_cross_section_absence_clause():
    body='## Question\n\nThe causes remain an open question.\n\n[01:00]\n\n## Answer\n\nThe later discussion proposes reward reinforcement.\n\n> An original quote.\n'
    def call(system,payload,timeout):
        data=json.loads(payload)
        assert timeout==60 and len(data['paragraphs'])==3
        assert data['transition_candidates']==['P1']
        return {'overview':'The discussion proposes a mechanism.', 'transitions':[{
            'paragraph_id':'P1','old':'remain an open question','new':'are discussed later',
            'answer_paragraph_ids':['P3']}]} 
    edited,overview,report=compose_overview('Title',[],body,call,250,'en')
    assert edited==body.replace('remain an open question','are discussed later')
    assert report['transition_repairs']==1
    assert overview=='The discussion proposes a mechanism.'


def test_invalid_transition_cannot_rewrite_unrelated_prose_or_source_quote():
    body='A valid claim.\n\nA question is unanswered.\n\n> The source question is unanswered.\n'
    edits=[{'paragraph_id':'P1','old':'A valid claim.','new':'Changed','answer_paragraph_ids':['P2']},
           {'paragraph_id':'P2','old':'unanswered','new':'solved','answer_paragraph_ids':['missing']},
           {'paragraph_id':[],'old':'unanswered','new':'solved','answer_paragraph_ids':['P1']}]
    result,_,report=compose_overview('Title',[],body,Mock(return_value={'overview':'Intro','transitions':edits}),250,'en')
    assert result==body and report['invalid_transition_repairs']==3


def test_chunk_merge_defers_one_overview_until_complete_reading_draft():
    engine=NoteSummarizer(api_key='fixture');engine.generation_report={}
    engine._editorial_json=Mock(return_value={'overview':'A supported conclusion.','transitions':[]})
    body=engine._merge_chunk_notes('Title',['## Argument\n\nEvidence.\n\n## AI Summary\n\nImportant condition.'],False,whole_summary=True,defer_overview=True)
    engine._editorial_json.assert_not_called()
    assert 'Important condition.' in body
    result=engine._complete_overview(body,'Title')
    assert engine._editorial_json.call_count==1 and 'A supported conclusion.' in result
    engine._editorial_json.side_effect=TimeoutError()
    assert engine._complete_overview(body,'Title')==body
    assert engine.generation_report['overview']['reason']=='timeout'


def test_partial_raw_transcript_never_receives_a_misleading_whole_video_intro():
    from summary_errors import delivery_notice
    engine=NoteSummarizer(api_key='fixture');engine.generation_report={}
    engine._pending_overview=['Only the successful section.']
    engine._editorial_json=Mock()
    body=delivery_notice('## Original transcript\n\nThis section was not summarized.',source='English source')
    assert engine._complete_overview(body,'Title')==body
    engine._editorial_json.assert_not_called()
    assert engine.generation_report['overview']['reason']=='raw_source_retained'
