import json
from unittest.mock import Mock

import pytest

from note_presentation import chronological_chapters, media_times, localize_note, language_mismatch, without_generated_toc
from reading_editor import edit_sections
from summary_errors import ProcessingCancelledError


def test_whole_video_chapters_and_recurring_subtopics_follow_media_time_without_losing_content():
    source='# Title\n\n## Introduction\n\nOriginal introduction.\n\n## 1. Growth\n\n### 1.1 Early\n\nFirst condition.\nScreenshot-[00:46]\n\n### 1.2 Later example\n\nLater condition.\nScreenshot-[09:29]\n\n## 2. Habits\n\nThird book.\nScreenshot-[03:50]\n\n## AI Summary\n\nWhole-video conclusion.\n'
    result=chronological_chapters(source)
    assert media_times(result)==[46,230,569]
    for text in ['Original introduction.','First condition.','Later condition.','Third book.','Whole-video conclusion.']:
        assert result.count(text)==1
    assert result.index('Third book.')<result.index('Later condition.')
    assert result.endswith('Whole-video conclusion.\n')
    assert chronological_chapters(result)==result
    assert chronological_chapters('Plain complete source.')=='Plain complete source.'


def test_times_in_quotes_and_code_do_not_move_chapters_or_rewrite_markers():
    source='## First\nScreenshot-[02:00]\n\n> Screenshot-[00:01]\n\n```md\nScreenshot-[00:02]\n```\n\n## Earlier\nScreenshot-[01:00]\n'
    result=chronological_chapters(source)
    assert media_times(result)==[60,120]
    assert '> Screenshot-[00:01]' in result and '```md\nScreenshot-[00:02]\n```' in result


def test_conclusion_keeps_a_heading_boundary_when_the_last_chapter_has_no_final_newline():
    source='## AI Summary\n\nWhole conclusion.\n\n## Final chapter\n\nScreenshot-[03:00]\n\nFinal argument.\n\n---'
    result=chronological_chapters(source)
    assert '---\n\n## AI Summary' in result
    assert '---##' not in result


def test_video_editor_rejects_nonadjacent_groups_without_failing_or_dropping_rows():
    rows=[{'id':f'N{i}','topic':name,'text':f'Original {i}.'} for i,name in enumerate(['Growth','Habits','Growth'],1)]
    call=Mock(return_value={'groups':[{'title':'Growth','ids':['N1','N3']},{'title':'Habits','ids':['N2']}]})
    result=edit_sections(rows,call,preserve_order=True,source_text='Original English speech.')
    assert [r['ids'] for r in result]==[['N1'],['N2'],['N3']]
    assert [r['text'] for r in result]==[r['text'] for r in rows]
    assert call.call_count==1
    assert 'Original English speech.' in call.call_args.args[0]


def test_recurring_chapter_names_do_not_merge_back_across_an_intervening_chapter():
    rows=[{'id':f'N{i}','topic':name,'text':f'Original {i}.'} for i,name in enumerate(['Growth','Habits','Growth'],1)]
    call=Mock(return_value={'groups':[{'title':r['topic'],'ids':[r['id']]} for r in rows]})
    result=edit_sections(rows,call,preserve_order=True)
    assert [r['ids'] for r in result]==[['N1'],['N2'],['N3']]


def test_language_only_correction_uses_original_language_and_preserves_source_blocks():
    source='The speaker explains how verification and architecture constrain agents.'
    draft='## 2. 验证系统\n\n需要保留 2 个条件。\nScreenshot-[01:23]\n\n> Verbatim quote with 3 details.\n\n```py\nprint("原始代码")\n```\n\n'
    def call(system,payload,timeout):
        assert source in system and timeout<=45
        raw=json.loads(payload)['markdown']
        return {'text':raw.replace('验证系统','Verification').replace('需要保留 2 个条件。','Retain 2 conditions.')}
    result=localize_note(draft,source,call)
    assert '## 2. Verification' in result and 'Retain 2 conditions.' in result
    assert '> Verbatim quote with 3 details.' in result and 'print("原始代码")' in result
    assert 'Screenshot-[01:23]' in result and not language_mismatch(source,result)


def test_language_correction_accepts_equivalent_chinese_numeric_spacing_and_magnitudes():
    draft='## 处理条件\n\n保留2个条件，处理3万 tokens。软件 v1.2.3。\n'
    translated='## Conditions\n\nRetain 2 conditions and process 30,000 tokens. Software v1.2.3.\n'
    assert localize_note(draft,'The original English source.',lambda *args:{'text':translated})==translated


@pytest.mark.parametrize('change',[lambda text:text.replace('2','3'),lambda text:text.replace('Screenshot-[01:23]',''),lambda text:text+'\n## New claim'])
def test_invalid_language_repair_keeps_readable_original_instead_of_failing(change):
    draft='## 条件说明\n\n保留 2 个条件。\nScreenshot-[01:23]\n'
    call=lambda *args:{'text':change('## Conditions\n\nRetain 2 conditions.\nScreenshot-[01:23]\n')}
    assert localize_note(draft,'The original English speech.',call)==draft


def test_language_cancellation_propagates_and_unavailable_provider_keeps_the_note():
    draft='## 原文条件\n\n保留所有原文内容。\n'
    assert localize_note(draft,'English original speech.',Mock(side_effect=RuntimeError()))==draft
    with pytest.raises(ProcessingCancelledError):
        localize_note(draft,'English original speech.',Mock(side_effect=ProcessingCancelledError()))
    call=Mock(side_effect=RuntimeError())
    assert localize_note(draft+'\n## 另一个章节\n\n完整条件。','English original speech.',call).startswith(draft)
    assert call.call_count==2  # Independent sections get their own bounded attempt.


def test_rejected_translation_reports_only_check_names_without_source_or_provider_data():
    report={}
    draft='## 条件说明\n\n保留 2 个条件。\n'
    translated='## Conditions\n\nRetain 3 conditions.\n'
    assert localize_note(draft,'Original English source.',lambda *args:{'text':translated},report=report)==draft
    assert report=={'attempted':1,'rejected_checks':{'numeric_values':1},'retained':1}


def test_generated_contents_are_removed_without_removing_real_contents_discussions():
    source='# Title\n\n## 1. Contents\n- [Chapter](#chapter)\n\n---\n\n## Chapter\n\nOriginal body.\n'
    result=without_generated_toc(source)
    assert 'Contents' not in result and 'Original body.' in result
    real='## Contents\n\nThe contents of this agreement matter.\n\n- First condition\n'
    assert without_generated_toc(real)==real


def test_audited_additions_keep_their_real_source_position_instead_of_the_append_position():
    from note_summarizer import NoteSummarizer
    from source_coverage import SourceReview
    from unittest.mock import patch
    engine=NoteSummarizer(api_key='synthetic')
    review=SourceReview({'body':'## Later\n\nScreenshot-[03:00]\n\nLater argument.\n'},
        [{'heading':'Earlier condition','text':'Original earlier condition.','source_quote':'The earlier condition matters.','timestamp':'03:00'}],{})
    with patch('note_summarizer.audit_source',return_value=review):
        result=engine._audit_note_verified('[01:00] The earlier condition matters.\n[03:00] Later argument.', 'Draft')
    assert '[01:00]' in result
    assert '[03:00]\n\nOriginal earlier condition.' not in result


def test_reported_repair_preserves_the_original_post_suffix_and_does_not_split_code_examples():
    from scripts.repair_note_presentation import original_suffix
    prefix='# Title\n\n## Argument\n\n```md\n## Original post / article\nLiteral example.\n```\n\n'
    suffix='## Original post / article\n\n> Complete original post and media link.\n'
    assert original_suffix(prefix+suffix)==(prefix,suffix)


def test_finished_reader_uses_persisted_revision_while_running_and_dirty_tasks_keep_progress_cache():
    import threading
    from video_task_db import _SupabaseVideoTaskDB
    backend=_SupabaseVideoTaskDB.__new__(_SupabaseVideoTaskDB)
    backend._lock=threading.Lock();backend._dirty={}
    backend._cache={'note':{'id':'note','user_id':'owner','status':'success','markdown':'Old cached note'}}
    backend._sb=Mock();backend._sb.get_video_task.return_value={'id':'note','markdown':'Repaired persisted note'}
    assert backend.get_task('note','owner',include_transcript=False)['markdown']=='Repaired persisted note'
    backend._sb.get_video_task.assert_called_once_with('note','owner',include_transcript=False)
    backend._sb.get_video_task.reset_mock()
    backend._cache['note']['status']='summarizing'
    assert backend.get_task('note','owner',include_transcript=False)['markdown']=='Old cached note'
    backend._sb.get_video_task.assert_not_called()
    backend._cache['note']['status']='success';backend._dirty={'note':{'markdown':'Unsaved final note'}}
    assert backend.get_task('note','owner',include_transcript=False)['markdown']=='Old cached note'
    backend._sb.get_video_task.assert_not_called()
