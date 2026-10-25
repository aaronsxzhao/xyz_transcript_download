import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
from reading_editor import edit_sections, call_editor
from summary_errors import ProcessingCancelledError, delivery_notice


def notes():
    return [{'id':'N1','topic':'Policy background','text':'#### Purpose\n\nProtect buyers and adapt to changing demand.','evidence':'Protect buyers.'},
            {'id':'N2','topic':'Two policy goals','text':'#### Demand conditions\n\nProtect buyers; if demand falls, reassess supply.','evidence':'If demand falls, reassess supply.'}]


def replies(text='The reform protects buyers and adapts to demand. If demand falls, supply must be reassessed.'):
    return [{'groups':[{'title':'Reform goals and limits','ids':['N1','N2']}]},
            {'paragraphs':[{'heading':'Purpose and demand conditions','text':text,'ids':['N1','N2'],'evidence_id':'N2'}]},
            {'complete':True,'grounded':True}]


def test_related_points_become_one_coherent_passage_without_modifying_inputs():
    source=notes();before=copy.deepcopy(source);call=Mock(side_effect=replies())
    result=edit_sections(source,call)
    assert len(result)==1 and result[0]['ids']==['N1','N2']
    assert 'If demand falls, supply must be reassessed.' in result[0]['text']
    assert result[0]['topic']=='Reform goals and limits'
    assert result[0]['evidence_id']=='N2'
    assert source==before
    assert 'reassess supply' in json.loads(call.call_args_list[1].args[1])['notes'][1]['text']
    assert json.loads(call.call_args_list[2].args[1])['chapter']=='Reform goals and limits'


@pytest.mark.parametrize('ids',[['N1'],['N1','N1'],['N1','invented'],[]])
def test_missing_duplicate_or_invented_point_ids_cannot_discard_input(ids):
    data=replies();data[1]['paragraphs'][0]['ids']=ids
    result=edit_sections(notes(),Mock(side_effect=data))
    assert [row['text'] for row in result]==[row['text'] for row in notes()]
    assert [row['ids'] for row in result]==[['N1'],['N2']]
    assert [row['topic'] for row in result]==[row['topic'] for row in notes()]


@pytest.mark.parametrize('review',[{'complete':False,'grounded':True},{'complete':True,'grounded':False},{}])
def test_omitted_conditions_or_added_interpretation_keeps_original_notes(review):
    data=replies('This policy guarantees a housing recovery.');data[2]=review
    result=edit_sections(notes(),Mock(side_effect=data))
    assert 'guarantees' not in '\n'.join(row['text'] for row in result)
    assert 'if demand falls' in result[1]['text']


def test_video_edit_cannot_discard_charts_or_playback_positions():
    source=notes();source[1]['text']+='\nScreenshot-[02:30]\n*Content-[02:30]'
    call=Mock(side_effect=replies())
    result=edit_sections(source,call)
    assert 'Screenshot-[02:30]' in result[1]['text']
    assert '*Content-[02:30]' in result[1]['text']
    assert call.call_count==2  # Do not spend a review call on missing media.


@pytest.mark.parametrize('protected',[
    '> If demand falls, reassess supply.\n> This is conditional, not guaranteed.',
    '```python\nif demand_falls:\n    reassess_supply()\n```',
    '    if demand_falls:\n        reassess_supply()',
])
def test_semantically_similar_rewrite_cannot_replace_verbatim_quotes_or_code(protected):
    source=notes();source[1]['text']+='\n\n'+protected
    result=edit_sections(source,Mock(side_effect=replies()))
    assert protected in result[1]['text']
    assert [row['text'] for row in result]==[row['text'] for row in source]


def test_connected_prose_can_keep_exact_quote_and_code_blocks():
    source=notes();quote='> If demand falls, reassess supply.';code='```python\nreassess_supply()\n```'
    source[0]['text']+='\n\n'+quote;source[1]['text']+='\n\n'+code
    response=replies('The reform protects buyers; falling demand changes the supply assessment.\n\n'+quote+'\n\n'+code)
    result=edit_sections(source,Mock(side_effect=response))
    assert len(result)==1 and quote in result[0]['text'] and code in result[0]['text']


def test_composition_does_not_strip_indentation_from_an_opening_code_block():
    source=notes();code='    if demand_falls:\n        reassess_supply()'
    source[0]['text']=code
    response=replies(code+'\n\nProtect buyers; if demand falls, reassess supply.')
    result=edit_sections(source,Mock(side_effect=response))
    assert len(result)==1 and '\n\n'+code in result[0]['text']


def test_unavailable_provider_has_no_retry_cascade_and_preserves_readable_output():
    call=Mock(side_effect=RuntimeError('Synthetic provider outage'))
    source=notes();source[1]['topic']=source[0]['topic']
    result=edit_sections(source,call)
    assert [row['text'] for row in result]==[row['text'] for row in source]
    assert call.call_count==1


def test_budget_exhaustion_does_not_lose_remaining_notes():
    call=Mock()
    result=edit_sections(notes(),call,budget=0)
    assert [row['text'] for row in result]==[row['text'] for row in notes()]
    call.assert_not_called()


def test_cancellation_is_not_swallowed_by_optional_editing():
    with pytest.raises(ProcessingCancelledError):
        edit_sections(notes(),Mock(),checkpoint=Mock(side_effect=ProcessingCancelledError('stop')))


def test_podcast_composition_keeps_representative_verbatim_evidence_and_timestamp():
    from summarizer import Summarizer,Summary,KeyPoint
    engine=Summarizer(api_key='synthetic',base_url='https://model.example/v1',model='selected-model')
    original=Summary('ep','Original title','Overview',[KeyPoint('A',notes()[0]['text'],'Protect buyers.','01:00'),KeyPoint('B',notes()[1]['text'],'If demand falls, reassess supply.','02:00')],['A','B'],['Takeaway'])
    with patch.object(engine,'_editorial_json',side_effect=replies()):
        final=engine._edit_reading(original)
    assert final.title=='Original title' and final.takeaways==['Takeaway']
    assert len(final.key_points)==1
    assert final.key_points[0].original_quote=='If demand falls, reassess supply.'
    assert final.key_points[0].timestamp=='02:00'
    assert len(original.key_points)==2


def test_video_composition_keeps_intro_media_and_regenerates_contents():
    from note_summarizer import NoteSummarizer
    engine=NoteSummarizer(api_key='synthetic')
    draft='# Original title\n\nOriginal introduction.\n\n## 目录\n\n- [A](#a)\n\n## 1. First route\n\nProtect buyers.\n\n## 2. Second route\n\nIf demand falls, reassess supply.\n\nScreenshot-[02:30]'
    data=replies('Protect buyers. If demand falls, reassess supply.\n\nScreenshot-[02:30]')
    # Generated navigation is not a source note, so section IDs start at N2.
    data[0]['groups'][0]['ids']=['N2','N3']
    data[1]['paragraphs'][0].update(ids=['N2','N3'],evidence_id='N3')
    with patch.object(engine,'_editorial_json',side_effect=data):
        final=engine._edit_reading(draft,'Original title',True)
    assert final.count('# Original title')==1
    assert 'Original introduction.' in final and 'Screenshot-[02:30]' in final
    assert 'Reform goals and limits' in final and '[A](#a)' not in final
    assert '### 1.1 Purpose and demand conditions' in final
    assert '[1.1 Purpose and demand conditions]' in final
    assert 'N2' not in final and 'N3' not in final


def test_optional_editor_uses_selected_provider_client_and_model_without_retries():
    client=Mock();client.with_options.return_value.chat.completions.create.return_value=NS(choices=[NS(finish_reason='stop',message=NS(content='{"groups":[]}'))])
    assert call_editor(client,'selected-model','system','payload',12)=={'groups':[]}
    client.with_options.assert_called_once_with(timeout=12,max_retries=0)
    assert client.with_options.return_value.chat.completions.create.call_args.kwargs['model']=='selected-model'


def test_video_table_of_contents_with_real_prose_is_not_discarded():
    from note_summarizer import NoteSummarizer
    engine=NoteSummarizer(api_key='synthetic')
    source='# Title\n\n## Table of Contents\n\nAn independent source qualification.\n\n- [Details](#details)\n\n## Details\n\nReal source discussion.'
    with patch.object(engine,'_editorial_json',side_effect=RuntimeError('Synthetic outage')):
        final=engine._edit_reading(source,'Title',True)
    assert 'An independent source qualification.' in final
    assert 'Real source discussion.' in final


@pytest.mark.parametrize('add_toc', [False, True])
def test_video_editor_preserves_indented_code_in_intro_and_chapter_on_provider_failure(add_toc):
    from markdown_it import MarkdownIt
    from note_summarizer import NoteSummarizer
    engine = NoteSummarizer(api_key='synthetic')
    source = "# Title\n\n    intro()\n    prepare()\n\n## First\n\n    first()\n    second()\n\n## Second\n\nAn independent explanation."
    code_blocks = lambda value: [t.content for t in MarkdownIt().parse(value) if t.type == 'code_block']
    with patch.object(engine, '_editorial_json', side_effect=TimeoutError('Synthetic outage')):
        final = engine._edit_reading(source, 'Title', add_toc)
    assert code_blocks(final) == code_blocks(source)
    assert 'An independent explanation.' in final


def test_groq_editor_has_the_same_output_room_as_the_paid_summary_path():
    client=Mock(base_url='https://api.groq.com/openai/v1/')
    client.with_options.return_value.chat.completions.create.return_value=NS(choices=[NS(finish_reason='stop',message=NS(content='{"groups":[]}'))])
    call_editor(client,'openai/gpt-oss-120b','system','payload',12)
    options=client.with_options.return_value.chat.completions.create.call_args.kwargs
    assert options['max_completion_tokens']==32768 and options['reasoning_effort']=='medium'


@pytest.mark.parametrize('video',[False,True])
@pytest.mark.parametrize('long',[False,True])
def test_new_short_and_long_generations_apply_editorial_pass(video,long):
    if video:
        from note_summarizer import NoteSummarizer
        engine=NoteSummarizer(api_key='synthetic');engine.chunk_chars=1 if long else 10000
        with patch.object(engine,'_generate_chunked' if long else '_generate_single',return_value='# Draft') as generate,patch.object(engine,'_edit_reading',return_value='# Edited') as edit:
            assert '# Edited' in engine.generate_note('Title','Complete source transcript.')
    else:
        from summarizer import Summarizer,Summary
        from transcriber import Transcript
        engine=Summarizer(api_key='synthetic');engine.chunk_chars=1 if long else 10000
        draft=Summary('ep','Title','Draft',[],[],[]);edited=Summary('ep','Title','Edited',[],[],[])
        with patch('transcript_quality.validate_transcript'),patch.object(engine,'_summarize_long_transcript' if long else '_summarize_single',return_value=draft) as generate,patch.object(engine,'_edit_reading',return_value=edited) as edit:
            assert engine.summarize(Transcript('ep','en',120,'Complete source transcript.',[])) is edited
    generate.assert_called_once()
    edit.assert_called_once()


@pytest.mark.parametrize('video',[True,False])
def test_raw_source_fallbacks_are_not_disguised_as_finished_narrative(video):
    if video:
        from note_summarizer import NoteSummarizer
        engine=NoteSummarizer(api_key='synthetic')
        source=delivery_notice('# Title\n\n## Raw source\nComplete raw text.\n\n## Notes\nOther notes.','generation','English')
        with patch.object(engine,'_editorial_json') as call:
            assert engine._edit_reading(source,'Title',True)==source
    else:
        from summarizer import Summarizer,Summary,KeyPoint
        engine=Summarizer(api_key='synthetic')
        source=Summary('ep','Title',delivery_notice('Overview','generation','English'),[KeyPoint('A','Raw text','',''),KeyPoint('B','Other notes','','')],['A','B'],[])
        with patch.object(engine,'_editorial_json') as call:
            assert engine._edit_reading(source) is source
    call.assert_not_called()
