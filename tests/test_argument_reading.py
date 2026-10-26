"""Editorial behavior: source language, retained evidence, resumable diagnostics."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from reading_language import LANGUAGE, source_language, source_language_lock
from reading_prompts import podcast_prompt
from podcast_prompts import SYSTEM_PROMPT
from processing_execution import Execution, bind, parallel_map
from reading_generation import generation_session
from note_presentation import language_mismatch, localize_note
from note_summarizer import _build_system_prompt
from reading_editor import edit_sections


def test_english_dominant_source_with_chinese_aside_does_not_disable_detection():
    source='A discussion of source evidence and its limitations. '*30+'中文插话。'
    assert source_language(source)=='en'
    assert language_mismatch(source,'## 中文正文\n\n这一整段都写成了中文。')
    assert not language_mismatch(source,'## Evidence\n\nThe evidence is conditional.\n\n> 中文原话。')


def test_full_speech_not_only_intro_determines_language():
    source='An English sponsor introduction. '*20+'正文讨论条件和证据。'*1000
    assert source_language(source)=='zh'
    assert 'Target language = zh' in source_language_lock(source)
    assert '正文讨论' in source_language_lock(source)


def test_fixed_language_survives_parallel_minority_chunks_and_resets():
    token=LANGUAGE.set('en')
    try:
        assert parallel_map(source_language,['纯中文片段。','English section.'])==['en','en']
    finally: LANGUAGE.reset(token)
    assert source_language('纯中文片段。')=='zh'


def test_explicit_other_original_language_is_not_reclassified_as_english():
    assert source_language('Una explicación del argumento.', 'es')=='es'
    assert source_language('Una explicación del argumento y sus condiciones.')=='original'


def test_localized_templates_share_schema_without_chinese_example_leakage():
    english=podcast_prompt(SYSTEM_PROMPT,'English source.')
    assert '核心结论' not in english and '### Key conclusions' in english
    chinese=podcast_prompt(SYSTEM_PROMPT,'中文原文。')
    assert '### 核心结论' in chinese
    for prompt in (english,chinese):
        assert '"key_points"' in prompt and '"original_quote"' in prompt
    video=_build_system_prompt('business',['summary','screenshot'],source_text='English source.')
    assert not any('\u3400'<=c<='\u9fff' for c in video)
    assert 'Screenshot-[MM:SS]' in video and '## AI Summary' in video
    assert '### Key conclusions' not in video and '### Episode overview' not in video


def test_generation_identity_is_saved_with_work_without_keys_or_source():
    class Engine:
        model='selected-model';model_options={'reasoning_effort':'high'}
        api_key='private-key'
        @generation_session
        def generate(self,transcript_text):
            assert source_language('少量中文')=='en'
            return 'Generated result'
    execution=Execution('owner','source',Mock())
    with bind(execution):
        engine=Engine();engine.generate('The complete original English speech.')
    identity=execution.snapshot()['generation']
    assert identity['source_language']=='en' and identity['generated']
    assert len(identity['source_sha256'])==64
    assert identity['model_options']=={'reasoning_effort':'high'}
    assert 'private-key' not in json.dumps(identity) and 'complete original' not in json.dumps(identity)


def test_large_language_section_splits_only_at_real_block_boundaries():
    source='English source.'
    quote='> 中文原话保持逐字不变。'
    code='```python\nprint("中文代码")\n```'
    draft='## 条件\n\n'+('中文段落。'*100+'\n\n')*30+quote+'\n\n'+code+'\n'
    seen=[]
    def translate(system,payload,timeout):
        text=json.loads(payload)['markdown'];seen.append(text)
        return {'text':text.replace('条件','Conditions').replace('中文段落。','An English paragraph. ')}
    result=localize_note(draft,source,translate)
    assert len(seen)>1 and all(len(piece)<=14000 for piece in seen)
    assert quote in result and code in result
    assert not language_mismatch(source,result)


def test_one_slow_chapter_does_not_exhaust_later_chapter_allowance():
    now=[0]
    rows=[{'id':f'N{i}','topic':'A' if i<3 else 'B','text':f'Original detail {i}.'} for i in range(1,5)]
    def call(system,payload,timeout):
        data=json.loads(payload)
        if 'index' in data:return {'groups':[{'title':'A','ids':['N1','N2']},{'title':'B','ids':['N3','N4']}]}
        if 'rewrite' in data:return {'complete':True,'grounded':True}
        if data['chapter']=='A':now[0]+=95
        ids=[r['id'] for r in data['notes']]
        return {'paragraphs':[{'heading':'Connected argument','text':' '.join(r['text'] for r in data['notes']),'ids':ids,'evidence_id':ids[0]}]}
    report={}
    with patch('reading_editor.time.monotonic',side_effect=lambda:now[0]):
        result=edit_sections(rows,call,budget=None,report=report)
    assert [row['ids'] for row in result]==[['N1'],['N2'],['N3','N4']]
    assert report['retained_batches']==1 and report['composed_batches']==1


def test_independent_chapters_edit_in_parallel_but_return_in_source_order():
    import threading
    barrier=threading.Barrier(2)
    rows=[{'id':f'N{i}','topic':'A' if i<3 else 'B','text':f'Detail {i}.'} for i in range(1,5)]
    def call(system,payload,timeout):
        data=json.loads(payload)
        if 'index' in data:return {'groups':[{'title':'A','ids':['N1','N2']},{'title':'B','ids':['N3','N4']}]}
        if 'rewrite' in data:return {'complete':True,'grounded':True}
        barrier.wait(timeout=3)
        ids=[r['id'] for r in data['notes']]
        return {'paragraphs':[{'heading':'Argument','text':' '.join(r['text'] for r in data['notes']),'ids':ids,'evidence_id':ids[0]}]}
    report={}
    result=edit_sections(rows,call,budget=None,report=report)
    assert [row['ids'] for row in result]==[['N1','N2'],['N3','N4']]
    assert report['composed_batches']==2 and not report['retained_batches']


def test_merged_podcast_keeps_every_verified_quote_and_its_anchor():
    from summarizer import Summarizer, Summary, KeyPoint
    engine=Summarizer(api_key='fixture')
    note=Summary('ep','Title','Overview',[KeyPoint('A','Claim one.','First exact quote.','01:00'),KeyPoint('B','Same claim with a condition.','Second exact quote.','02:00')],['A','B'],[])
    replies=[{'groups':[{'title':'Argument','ids':['N1','N2']}]},
             {'paragraphs':[{'heading':'Claim and condition','text':'The claim holds under this condition.','ids':['N1','N2'],'evidence_id':'N2'}]},
             {'complete':True,'grounded':True}]
    with patch.object(engine,'_editorial_json',side_effect=replies):result=engine._edit_reading(note)
    point=result.key_points[0]
    assert point.original_quote=='Second exact quote.' and point.timestamp=='02:00'
    assert '> First exact quote.' in point.summary and '[01:00]' in point.summary


def test_video_conclusions_are_an_entry_layer_without_reordering_source_chapters():
    from note_summarizer import NoteSummarizer
    engine=NoteSummarizer(api_key='fixture')
    draft='# Title\n\n## First\n\nScreenshot-[01:00]\n\nOriginal first detail.\n\n## Second\n\nScreenshot-[02:00]\n\nOriginal second condition.\n\n## AI Summary\n\nThe central claim depends on that condition.\n'
    result=engine._finish_presentation(draft,'Title',False,'Original English source.')
    assert result.index('## AI Summary')<result.index('Original first detail.')<result.index('Original second condition.')
    assert result.count('The central claim depends on that condition.')==1


def test_language_correction_never_translates_raw_transcript_fallbacks():
    from summarizer import Summarizer,Summary,KeyPoint
    from note_summarizer import NoteSummarizer
    from summary_errors import delivery_notice
    source='Original English speech with an aside 中文原话。'
    summary=Summary('ep','Title',delivery_notice('Overview','generation',source),[KeyPoint('Original transcript',source,'','')],['Original transcript'],[])
    engine=Summarizer(api_key='fixture')
    with patch.object(engine,'_editorial_json') as call:
        assert engine._localize_summary(summary,source) is summary
    call.assert_not_called()
    engine=NoteSummarizer(api_key='fixture')
    with patch.object(engine,'_editorial_json') as call:
        result=engine._finish_presentation(delivery_notice('# Title\n\n## Original transcript\n\n'+source,'generation',source),'Title',False,source)
    call.assert_not_called()
    assert source in result
