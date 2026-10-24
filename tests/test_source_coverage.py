"""Coverage acceptance, evidence, failed audits and lossless assembly."""
import json
from dataclasses import asdict
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from source_coverage import audit_source, split_source, SOURCE_CHUNK_CHARS
from summarizer import Summarizer, Summary, KeyPoint
from note_summarizer import NoteSummarizer, _build_system_prompt
from summary_errors import SummaryOutputError


def receipt(unit="S1", field="point:0", note="不含中国"):
    return {"unit": unit, "kind": "content", "fields": [field]}


def result(data):
    return NS(choices=[NS(message=NS(content=json.dumps(data, ensure_ascii=False)))])


@pytest.mark.parametrize("source", ["", "甲乙。\n" * 2000 + "末尾的新论点", "x" * 17001, "第一句。\n\n第二句！ final sentence. " * 1000])
def test_partition_preserves_every_character_and_tail(source):
    chunks = split_source(source)
    assert "".join(chunks) == source
    assert all(0 < len(chunk) <= SOURCE_CHUNK_CHARS for chunk in chunks)


def test_audit_repairs_scope_and_percentage_points_and_appends_independent_example():
    source = "库存不含中国为12%，下降1个百分点。B50若落地增加需求200万吨。"
    audit = {
        "edits": [{"field": "point:0", "text": "库存不含中国为12%，下降1个百分点。", "source_ids": ["S1"]}],
        "additions": [{"id": "added:0", "topic": "需求", "heading": "政策情景", "text": "B50若落地增加需求200万吨。", "source_ids": ["S1"], "timestamp": "01:00:00"}],
        "coverage": [receipt()],
    }
    updated, additions, citations = audit_source(source, {"point:0": "全球库存12%，下降1%。"}, lambda *args: audit)
    assert updated["point:0"] == "库存不含中国为12%，下降1个百分点。"
    assert "若落地" in updated["added:0"]
    assert additions[0]["timestamp"] == ""  # invented time is never linked
    assert citations["point:0"] == source and additions[0]["source_quote"] == source


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "fake_source", "fake_note", "bad_skip", "wrong_field", "wrong_patch"])
def test_invalid_receipt_or_patch_cannot_pass_even_on_retry(mutation):
    data = {"edits": [], "additions": [], "coverage": [receipt()]}
    if mutation == "missing": data["coverage"] = []
    if mutation == "duplicate": data["coverage"] *= 2
    if mutation == "unknown": data["coverage"][0]["unit"] = "S9"
    if mutation == "fake_source": data["edits"] = [{"field": "point:0", "text": "changed", "source_ids": ["S99"]}]
    if mutation == "fake_note": data["coverage"][0]["fields"] = ["added:99"]
    if mutation == "bad_skip": data["coverage"][0].update(kind="non_content", reason="not important")
    if mutation == "wrong_field": data["coverage"][0]["fields"] = ["point:9"]
    if mutation == "wrong_patch": data["edits"] = [{"field": "point:0", "text": "changed", "source_ids": []}]
    call = Mock(return_value=data)
    with pytest.raises(SummaryOutputError, match="coverage"):
        audit_source("库存不含中国为12%，下降1个百分点。", {"point:0": "不含中国"}, call)
    assert call.call_count == 2


def test_audit_requires_every_source_unit_including_the_end():
    source = "甲" * 800 + "最后还有一个新情景，条件必须保留。" * 20
    with pytest.raises(SummaryOutputError):
        audit_source(source, {"point:0": "不含中国"}, lambda *args: {"coverage": [receipt()]})


def test_greetings_can_be_excluded_but_audits_do_not_drop_existing_fields():
    fields = {"point:0": "Existing explanation", "overview": "Introduction"}
    updated, additions, _ = audit_source("大家好，谢谢收听。", fields, lambda *args: {"coverage": [{"unit": "S1", "kind": "non_content", "reason": "greeting"}]})
    assert updated == fields and additions == []


def test_podcast_integrates_audit_additions_without_losing_prior_evidence():
    s = Summarizer(api_key="fixture", base_url="https://api.groq.com/openai/v1")
    source = "库存不含中国为12%，下降1个百分点。随后讨论可持续航空燃料。"
    draft = Summary("episode", "Original", "Intro", [KeyPoint("库存", "不含中国的库存为12%。", "库存不含中国为12%", "")], ["库存"], ["Keep conditions"])
    data = {"additions": [{"id": "added:0", "topic": "能源路径", "heading": "航空燃料", "text": "讨论可持续航空燃料。", "source_ids": ["S1"], "timestamp": ""}], "coverage": [receipt(field="point:1")]}
    with patch.object(s, "_call_llm_with_retry", return_value=result(data)):
        final = s._audit_summary(draft, source)
    assert final.key_points[0].summary == draft.key_points[0].summary
    assert final.key_points[0].original_quote == draft.key_points[0].original_quote
    assert final.key_points[1].topic == "能源路径"
    assert final.topics == ["库存", "能源路径"]
    assert final.takeaways == draft.takeaways


def test_video_audit_is_applied_to_body_and_additions_survive_merge():
    s = NoteSummarizer(api_key="fixture")
    data = {"additions": [{"id": "added:0", "topic": "实验", "heading": "失败分支", "text": "第一次45分钟，之后几次仍为45分钟。", "source_ids": ["S1"], "timestamp": ""}], "coverage": [receipt(field="added:0", note="仍为45分钟")]}
    with patch.object(s, "_call_llm", return_value=json.dumps(data, ensure_ascii=False)):
        audited = s._audit_note("之后几次仍为45分钟", "## 实验\n\n从1小时改善到45分钟。")
    merged = s._merge_chunk_notes("Original", [audited, "## 结尾\n\n最后一个条件。"], True)
    assert "从1小时改善到45分钟" in merged and "之后几次仍为45分钟" in merged and "最后一个条件" in merged


def test_video_keeps_all_chunk_conclusions_and_does_not_call_last_one_whole_episode():
    s = NoteSummarizer(api_key="fixture")
    final = s._merge_chunk_notes("Title", ["## A\nA details\n## AI 总结\nFirst condition", "## B\nB details\n## AI 总结\nLast condition"], False)
    assert "First condition" in final and "Last condition" in final
    assert "## Section conclusions" in final and "## AI 总结" not in final


def test_video_empty_chunk_keeps_earlier_notes_and_labels_the_raw_source_fallback():
    s = NoteSummarizer(api_key="fixture")
    with patch.object(s, "_call_llm", side_effect=["## First\nDetails", ""]), patch.object(s, "_audit_note", side_effect=lambda source, draft, callback, context: draft):
        result = s._generate_chunked("Title", "甲" * 4100, "detailed", [])
    assert 'Details' in result and '原始转写' in result
    assert '甲' * 100 in result


def test_every_style_keeps_substantive_information_and_source_headings():
    from note_summarizer import NOTE_STYLES
    for style in NOTE_STYLES:
        prompt = _build_system_prompt(style, [])
        assert "风格仅影响表达" in prompt and "不允许删掉独立信息" in prompt
        assert "原有有意义的章节标题尽量沿用" in prompt


def test_incomplete_video_segments_never_replace_full_source_when_adding_screenshots():
    from source_coverage import video_source_text
    segments = [{"start": 0, "text": "第一段。"}, {"start": 3601, "text": "最后的条件。"}]
    source = "第一段。独立的中间讨论。最后的条件。"
    assert video_source_text(source, segments) == source
    assert video_source_text("第一段。 最后的条件。", segments) == "[00:00] 第一段。\n[60:01] 最后的条件。"


def test_video_verification_receipts_do_not_leak_into_streamed_preview():
    s = NoteSummarizer(api_key="fixture")
    data = {"coverage": [receipt(field="body", note="不含中国")]}
    def stream(system, payload, callback, **kwargs):
        callback(200, '{"coverage": [{"unit": "S1"')
        return json.dumps(data)
    preview = Mock()
    with patch.object(s, "_call_llm", side_effect=stream):
        assert s._audit_note("不含中国", "## 原有标题\n不含中国", preview) == "## 原有标题\n不含中国"
    preview.assert_called_once_with(200, "## 原有标题\n不含中国")


def test_audit_retry_returns_specific_feedback_and_keeps_the_original_source_and_draft():
    bad = {"coverage": [receipt(field="point:99")]}
    good = {"coverage": [receipt()]}
    calls = []
    def call(system, payload):
        calls.append(json.loads(payload))
        return bad if len(calls) == 1 else good
    fields = {"point:0": "不含中国"}
    updated, _, _ = audit_source("库存不含中国为12%，下降1个百分点。", fields, call)
    assert updated == fields
    assert calls[1]["source_units"] == calls[0]["source_units"]
    assert calls[1]["draft_fields"] == fields
    assert calls[1]["previous_audit"] == bad
    assert calls[1]["validation_feedback"] == {"issue": "invalid_note_reference", "unit": "S1", "allowed_fields": ["point:0"]}


def test_stable_field_correction_preserves_other_fields_and_requires_real_evidence():
    source = "第一条是预测，不是事实。第二条仍是有效案例。"
    fields = {"point:0": "#### 判断\n\n第一条已成事实。", "point:1": "第二条仍是有效案例。"}
    data = {"edits": [{"field": "point:0", "text": "#### 判断\n\n第一条是预测，不是事实。", "source_ids": ["S1"]}], "coverage": [receipt(note="是预测")]}
    updated, _, _ = audit_source(source, fields, lambda *args: data)
    assert updated["point:1"] == fields["point:1"]
    assert "是预测" in updated["point:0"]


def test_two_whole_field_edits_cannot_overwrite_each_others_corrections():
    edit = {"field": "point:0", "text": "不含中国", "source_ids": ["S1"]}
    with pytest.raises(SummaryOutputError) as caught:
        audit_source("不含中国", {"point:0": "不含中国"}, lambda *args: {"edits": [edit, edit], "coverage": [receipt()]})
    assert caught.value.audit_feedback["issue"] == "duplicate_edit_field"


def test_original_evidence_is_extracted_by_code_across_time_anchors():
    source = "[00:00:01] 不含中国\n[00:00:31] 库存为12%，下降1个百分点。"
    data = {"additions": [{"id": "added:0", "topic": "库存", "heading": "范围", "text": "不含中国的库存为12%。", "source_ids": ["S1"], "source_quote": "MODEL INVENTED QUOTE"}], "coverage": [receipt(field="added:0")]}
    _, additions, citations = audit_source(source, {}, lambda *args: data)
    expected = "不含中国\n库存为12%，下降1个百分点。"
    assert additions[0]["source_quote"] == expected == citations["added:0"]
    assert "MODEL" not in citations["added:0"]


def test_one_source_unit_can_cover_several_detailed_points_with_verbatim_evidence_for_each():
    source = "第一条是一个论点。第二条是一个反例。"
    data = {"coverage": [{"unit": "S1", "kind": "content", "fields": ["point:0", "point:1"]}]}
    fields = {"point:0": "#### 论点\n\n**第一条**。", "point:1": "#### 反例\n\n第二条。"}
    updated, _, citations = audit_source(source, fields, lambda *args: data)
    assert updated == fields
    assert citations == {"point:0": source, "point:1": source}


def test_an_overview_cannot_substitute_for_detailed_source_coverage():
    with pytest.raises(SummaryOutputError):
        audit_source("完整论据和案例。", {"overview": "一句话概览。", "point:0": "详细内容。"}, lambda *args: {"coverage": [receipt(field="overview")]})


def test_unmapped_source_gets_a_dedicated_passage_and_actual_evidence_instead_of_a_fake_receipt():
    source = "甲" * 800 + "第二段有一个独立反例，只有条件成立才有效。" + "补充说明。" * 50
    calls = []
    def call(system, payload):
        assert "json" in system.lower()  # Groq's json_object API requirement
        calls.append(json.loads(payload))
        if len(calls) == 1: return {"coverage": [receipt()]}
        return {"kind": "content", "topic": "反例", "heading": "反例的条件", "text": "第二段的独立反例只有在条件成立时才有效。"}
    updated, additions, citations = audit_source(source, {"point:0": "原有细节。"}, call)
    assert calls[1]["source_text"] == source[800:]
    assert "previous_audit" not in calls[1]
    assert updated["point:0"] == "原有细节。"
    assert "只有在条件成立时" in updated["added:1"]
    assert additions[0]["source_quote"] == source[800:] == citations["added:1"]


@pytest.mark.parametrize("response", [{}, {"kind": "unknown"}, {"kind": "content", "text": "Only an incomplete note"}])
def test_missing_source_cannot_pass_with_an_empty_unknown_or_incomplete_repair(response):
    calls = Mock(side_effect=[{"coverage": []}, response])
    with pytest.raises(SummaryOutputError):
        audit_source("源材料包含独立细节。", {"point:0": "Old note"}, calls)
    assert calls.call_count == 2


def test_addition_reference_uses_its_explicit_id_instead_of_array_position():
    data = {"additions": [{"id": "added:42", "topic": "案例", "heading": "条件", "text": "保留独立条件。", "source_ids": ["S1", "S1"]}], "coverage": [receipt(field="added:42")]}
    updated, additions, citations = audit_source("独立条件的原文。", {}, lambda *args: data)
    assert "added:42" in updated and "added:0" not in updated
    assert additions[0]["source_quote"] == citations["added:42"] == "独立条件的原文。"


def test_duplicate_explicit_addition_ids_cannot_overwrite_source_details():
    addition = {"id": "added:1", "topic": "案例", "heading": "条件", "text": "细节。", "source_ids": ["S1"]}
    with pytest.raises(SummaryOutputError):
        audit_source("细节原文。", {}, lambda *args: {"additions": [addition, addition], "coverage": [receipt(field="added:1")]})


def test_incremental_provider_repair_keeps_all_previous_added_details_and_references():
    source = "".join(character * 800 for character in "甲乙丙丁戊己")
    prior = {"additions": [{"id": f"added:{i}", "topic": "原有标题", "heading": f"细节{i}", "text": f"独立内容{i}", "source_ids": [f"S{i}"]} for i in range(1, 6)],
             "coverage": [{"unit": f"S{i}", "kind": "content", "fields": [f"added:{i}"]} for i in range(1, 7)]}
    # A real provider returned only the new fix while retaining references to
    # the five earlier additions. Treating this as a full replacement lost them.
    delta = {"additions": [{"id": "added:6", "topic": "原有标题", "heading": "细节6", "text": "独立内容6", "source_ids": ["S6"]}],
             "coverage": [{"unit": "S6", "kind": "content", "fields": ["added:6"]}]}
    call = Mock(side_effect=[prior, delta])
    updated, additions, citations = audit_source(source, {}, call)
    assert set(updated) == {f"added:{i}" for i in range(1, 7)}
    assert len(additions) == 6
    for i, character in enumerate("甲乙丙丁戊己", 1):
        assert f"独立内容{i}" in updated[f"added:{i}"]
        assert citations[f"added:{i}"] == character * 800
    assert call.call_count == 2


def test_short_asr_tail_keeps_its_context_and_every_original_character():
    from source_coverage import source_units
    source = ("甲" * 799 + "\n") * 5 + "我通过Astron怎么做computer use\n"
    units = source_units(source)
    assert "".join(units.values()) == source
    assert len(units) == 5
    assert units["S5"].endswith("我通过Astron怎么做computer use\n")
    assert all(len(text) >= 200 for text in units.values())


def test_content_receipt_with_null_fields_requires_a_real_source_passage_after_format_retry():
    source = "玉米基准560美分、峰值610美分，预测跨度三至六个月。"
    calls = Mock(side_effect=[{"coverage": [{"unit": "S1", "kind": "content", "fields": None}]},
                             {"coverage": [{"unit": "S1", "kind": "content", "fields": None}]},
                             {"kind": "content", "topic": "价格情景", "heading": "玉米目标价",
                              "text": "未来三至六个月，玉米基准560美分，峰值610美分。"}])
    updated, additions, citations = audit_source(source, {}, calls)
    assert updated["added:1"].endswith("未来三至六个月，玉米基准560美分，峰值610美分。")
    assert citations["added:1"] == source
    assert calls.call_count == 3
    assert json.loads(calls.call_args.args[1])["source_text"] == source


def test_new_chunks_receive_the_prior_meaningful_chapter_titles():
    from transcriber import Transcript
    engine = Summarizer(api_key="fixture")
    engine.chunk_chars = 100
    source = Transcript("episode", "zh", 300, "甲" * 100 + "乙" * 100, [])
    first = Summary("episode", "Title", "Overview", [], ["原文第一章"], [])
    second = Summary("episode", "Title", "Overview", [], ["原文第二章"], [])
    with patch.object(engine, "_summarize_single", side_effect=[first, second]) as extract, patch.object(engine, "_merge_summaries", return_value=second):
        engine._summarize_long_transcript(source, "Show", "Title")
    assert extract.call_args_list[0].args[5] == []
    assert extract.call_args_list[1].args[5] == ["原文第一章"]


def test_podcast_boundaries_keep_conditions_as_context_without_dropping_or_duplicating_source():
    from transcriber import Transcript
    engine = Summarizer(api_key="fixture")
    engine.chunk_chars = 150
    text = "甲" * 135 + "前提是排除中国。" + "乙" * 150 + "该条件仍然适用。"
    source = Transcript("episode", "zh", 300, text, [])
    draft = Summary("episode", "Title", "Overview", [], [], [])
    with patch.object(engine, "_summarize_single", return_value=draft) as extract, patch.object(engine, "_merge_summaries", return_value=draft):
        engine._summarize_long_transcript(source, "Show", "Title")
    requests = extract.call_args_list
    assert "".join(row.args[1] for row in requests) == text
    assert "前提是排除中国。" in requests[1].kwargs["source_context"]["before"]
    assert requests[0].kwargs["source_context"]["before"] == ""
    assert requests[-1].kwargs["source_context"]["after"] == ""


def test_audit_preserves_a_verified_original_quote_when_the_point_is_unchanged():
    s = Summarizer(api_key='fixture')
    source = '[00:00:01] 原有引用。\n同一段中其他观点。'
    draft = Summary('episode', 'Title', 'Overview', [KeyPoint('主题', '原有观点', '原有引用。', '00:00:01')], ['主题'], [])
    with patch('summarizer.audit_source', return_value=({'overview': 'Overview', 'point:1': '原有观点'}, [], {'point:1': '原有引用。\n同一段中其他观点。'})):
        final = s._audit_summary(draft, source)
    assert final.key_points[0].original_quote == '原有引用。'


def test_audit_preserves_a_point_without_fabricating_its_missing_quote():
    s = Summarizer(api_key='fixture')
    draft = Summary('episode', 'Title', 'Overview', [KeyPoint('主题', 'Unsupported detail', 'Invented evidence', '')], ['主题'], [])
    with patch('summarizer.audit_source', return_value=({'overview': 'Overview', 'point:1': 'Unsupported detail'}, [], {})):
        final = s._audit_summary(draft, 'The real source.')
    assert final.key_points[0].summary == 'Unsupported detail'
    assert final.key_points[0].original_quote == final.key_points[0].timestamp == ''
    assert 'coverage review did not complete' in final.overview


def test_changed_point_uses_its_new_audited_evidence_instead_of_old_quote():
    s = Summarizer(api_key='fixture')
    draft = Summary('episode', 'Title', 'Overview', [KeyPoint('主题', 'Old detail', '原有引用。', '')], ['主题'], [])
    with patch('summarizer.audit_source', return_value=({'overview': 'Overview', 'point:1': 'Corrected detail'}, [], {'point:1': '更正后的依据。'})):
        final = s._audit_summary(draft, '原有引用。更正后的依据。')
    assert final.key_points[0].original_quote == '更正后的依据。'


def test_audited_quote_cannot_keep_a_different_passages_real_timestamp():
    s = Summarizer(api_key='fixture')
    source = '[00:00:01] 旧观点。\n[00:01:02] 更正后的依据。'
    draft = Summary('episode', 'Title', 'Overview', [KeyPoint('主题', 'Old detail', '旧观点。', '00:00:01')], ['主题'], [])
    with patch('summarizer.audit_source', return_value=({'overview': 'Overview', 'point:1': 'Corrected detail'}, [], {'point:1': '更正后的依据。'})):
        final = s._audit_summary(draft, source)
    assert final.key_points[0].timestamp == '00:01:02'


def test_added_point_time_must_match_its_actual_evidence_too():
    s = Summarizer(api_key='fixture')
    draft = Summary('episode', 'Title', 'Overview', [], [], [])
    addition = {'id': 'added:1', 'topic': '主题', 'source_quote': '新增依据。', 'timestamp': '00:00:01'}
    with patch('summarizer.audit_source', return_value=({'overview': 'Overview', 'added:1': 'Added detail'}, [addition], {})):
        final = s._audit_summary(draft, '[00:00:01] 开场。\n[00:02:03] 新增依据。')
    assert final.key_points[0].timestamp == '00:02:03'


@pytest.mark.parametrize('source,quote,preferred,expected', [
    ('[00:01:02] Exact\n wording.', 'Exact wording.', '', '00:01:02'),
    ('Unsegmented source.', 'source.', '00:00:00', ''),
    ('[00:00:00] Same.\n[00:01:00] Same.', 'Same.', '', ''),
    ('[00:00:00] Same.\n[00:01:00] Same.', 'Same.', '00:01:00', '00:01:00'),
    ('[00:00:00] First.\n[00:01:00] Second.', 'Second.', '00:00:00', '00:01:00'),
    ('[00:00:00] Real source.', 'Invented quote.', '00:00:00', ''),
    ('[00:00:00] Real source.', '', '00:00:00', ''),
])
def test_evidence_time_uses_real_anchors_and_avoids_ambiguous_or_invented_times(source, quote, preferred, expected):
    from source_coverage import quote_timestamp
    assert quote_timestamp(source, quote, preferred) == expected
