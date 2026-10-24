"""Language follows the source; advisory review is distinct from missing output."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from reading_language import SOURCE_LANGUAGE
from summary_errors import delivery_notice, strip_delivery_notices, merge_delivery_notices
from note_summarizer import NoteSummarizer, _build_system_prompt
from podcast_prompts import SYSTEM_PROMPT, MERGE_SYSTEM_PROMPT
from source_coverage import audit_source
from video_downloader import original_subtitle_language
from transcriber import APITranscriber, Transcriber


def test_all_generation_and_audit_prompts_require_source_language():
    for prompt in (SYSTEM_PROMPT, MERGE_SYSTEM_PROMPT, _build_system_prompt('detailed', ['toc','summary'])):
        assert SOURCE_LANGUAGE in prompt
        assert 'information-rich Chinese reading notes' not in prompt
        assert 'Write reading passages in Chinese' not in prompt
    calls=[]
    def call(system,payload):
        calls.append(system)
        return {'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}
    audit_source('Source.', {'body':'Source.'}, call, repair=False)
    assert SOURCE_LANGUAGE in calls[0]
    assert '"point:1"' not in calls[0]
    assert '"fields":["body", "added:1"]' in calls[0]


def test_video_audit_requests_json_without_applying_json_mode_to_the_note():
    engine=NoteSummarizer(api_key='fixture')
    result=NS(choices=[NS(message=NS(content='{"coverage":[]}'), finish_reason='stop')])
    with patch.object(engine.client.chat.completions,'create',return_value=result) as create:
        engine._call_llm('Review JSON','Payload',json_output=True)
        assert create.call_args.kwargs['response_format']=={'type':'json_object'}
        engine._call_llm('Reading note','Source')
        assert 'response_format' not in create.call_args.kwargs


@pytest.mark.parametrize('language,subtitles,expected',[
    ('en', {'zh-Hans':{},'en':{}},'en'),
    ('zh', {'en':{},'zh-Hans':{}},'zh-Hans'),
    ('', {'zh-Hans':{},'en-orig':{}},'en-orig'),
    ('', {'zh':{}},None),
    ('en', {'zh':{}},None),
    ('es', {'es':{},'en':{}},'es'),
])
def test_translated_subtitles_cannot_override_original_audio_language(language, subtitles, expected):
    assert original_subtitle_language({'language':language},subtitles)==expected


def test_api_transcription_auto_detects_by_default_and_honors_explicit_language(tmp_path):
    audio=tmp_path/'audio.wav';audio.write_bytes(b'fixture')
    engine=APITranscriber(api_key='fixture')
    response=NS(text='This is the spoken English source. '*12,language='en',duration=5,segments=[])
    with patch.object(engine,'_wait_for_rate_limit'),patch.object(engine,'_get_audio_duration',return_value=5),patch.object(engine.client.audio.transcriptions,'create',return_value=response) as create:
        result=engine.transcribe(audio,'e')
        assert result.language=='en'
        assert 'language' not in create.call_args.kwargs
        engine.transcribe(audio,'e',language='en')
        assert create.call_args.kwargs['language']=='en'


def test_review_notice_never_claims_sections_failed_and_survives_merge():
    reviewed=delivery_notice('## Notes\nComplete generated draft.', 'audit', 'English source.')
    assert 'coverage review did not complete' in reviewed
    assert 'could not be summarized' not in reviewed
    assert strip_delivery_notices(reviewed)=='## Notes\nComplete generated draft.'
    engine=NoteSummarizer(api_key='fixture')
    merged=engine._merge_chunk_notes('Title',[reviewed, reviewed+'\nAnother detail'],True)
    assert merged.count('coverage review did not complete')==1
    assert '## Contents' in merged and '## 目录' not in merged
    assert 'Another detail' in merged
    missing=delivery_notice('## Part 2: Original transcript\nSource.',source='English source.')
    combined=merge_delivery_notices('All preserved.',[reviewed,missing])
    assert 'could not be summarized' in combined
    assert 'coverage review did not complete' in combined


def test_chinese_notices_are_specific_to_the_failure():
    review=delivery_notice('已生成正文','audit','中文原文')
    assert '全文覆盖核对未完成' in review
    assert '未总结的分段' not in review
    assert '部分分段未能生成摘要' in delivery_notice('原文已保留',source='中文原文')


def test_safe_live_language_probe_emits_only_boolean_results(monkeypatch):
    from scripts.probe_summary_language import probe_summary_language
    monkeypatch.setenv('GROQ_API_KEY','private-key')
    engine=Mock()
    engine._generate_single.side_effect=['## Notes\n'+'A correct English source explanation. '*10, '## 中文笔记\n'+'中文内容保持原样。'*10]
    with patch('note_summarizer.NoteSummarizer',return_value=engine):
        reports=probe_summary_language()
    assert [row['language_matches'] for row in reports]==[1,1]
    assert [row['audit_completed'] for row in reports]==[1,1]
    assert 'private-key' not in str(reports)
    assert 'source explanation' not in str(reports)


def test_notice_cleanup_preserves_quoted_source_and_code():
    from summary_errors import AUDIT_WARNING
    body='## Source example\n\n```markdown\n'+AUDIT_WARNING+'\n```'
    assert strip_delivery_notices(body)==body
    assert strip_delivery_notices(delivery_notice(body, 'audit'))==body
