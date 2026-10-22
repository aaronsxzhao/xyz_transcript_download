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
        "additions": [{"topic": "需求", "heading": "政策情景", "text": "B50若落地增加需求200万吨。", "source_ids": ["S1"], "timestamp": "01:00:00"}],
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
    source = "甲" * 800 + "最后还有一个新情景。"
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
    data = {"additions": [{"topic": "能源路径", "heading": "航空燃料", "text": "讨论可持续航空燃料。", "source_ids": ["S1"], "timestamp": ""}], "coverage": [receipt()]}
    with patch.object(s, "_call_llm_with_retry", return_value=result(data)):
        final = s._audit_summary(draft, source)
    assert final.key_points[0].summary == draft.key_points[0].summary
    assert final.key_points[0].original_quote == source
    assert final.key_points[1].topic == "能源路径"
    assert final.topics == ["库存", "能源路径"]
    assert final.takeaways == draft.takeaways


def test_video_audit_is_applied_to_body_and_additions_survive_merge():
    s = NoteSummarizer(api_key="fixture")
    data = {"additions": [{"topic": "实验", "heading": "失败分支", "text": "第一次45分钟，之后几次仍为45分钟。", "source_ids": ["S1"], "timestamp": ""}], "coverage": [receipt(field="added:0", note="仍为45分钟")]}
    with patch.object(s, "_call_llm", return_value=json.dumps(data, ensure_ascii=False)):
        audited = s._audit_note("之后几次仍为45分钟", "## 实验\n\n从1小时改善到45分钟。")
    merged = s._merge_chunk_notes("Original", [audited, "## 结尾\n\n最后一个条件。"], True)
    assert "从1小时改善到45分钟" in merged and "之后几次仍为45分钟" in merged and "最后一个条件" in merged


def test_video_keeps_all_chunk_conclusions_and_does_not_call_last_one_whole_episode():
    s = NoteSummarizer(api_key="fixture")
    final = s._merge_chunk_notes("Title", ["## A\nA details\n## AI 总结\nFirst condition", "## B\nB details\n## AI 总结\nLast condition"], False)
    assert "First condition" in final and "Last condition" in final
    assert "## 分段小结" in final and "## AI 总结" not in final


def test_video_empty_chunk_cannot_succeed_after_an_earlier_good_chunk():
    s = NoteSummarizer(api_key="fixture")
    with patch.object(s, "_call_llm", side_effect=["## First\nDetails", ""]), patch.object(s, "_audit_note", side_effect=lambda source, draft, callback: draft):
        with pytest.raises(SummaryOutputError):
            s._generate_chunked("Title", "甲" * 4100, "detailed", [])


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
    def stream(system, payload, callback):
        callback(200, '{"coverage": [{"unit": "S1"')
        return json.dumps(data)
    preview = Mock()
    with patch.object(s, "_call_llm", side_effect=stream):
        assert s._audit_note("不含中国", "## 原有标题\n不含中国", preview) == "## 原有标题\n不含中国"
    preview.assert_called_once_with(200, "## 原有标题\n不含中国")


def test_audit_retry_returns_specific_feedback_and_keeps_the_original_source_and_draft():
    bad = {"coverage": []}
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
    assert calls[1]["validation_feedback"] == {"issue": "missing_units", "missing_units": ["S1"]}


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
    data = {"additions": [{"topic": "库存", "heading": "范围", "text": "不含中国的库存为12%。", "source_ids": ["S1"], "source_quote": "MODEL INVENTED QUOTE"}], "coverage": [receipt(field="added:0")]}
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
