"""Reported repairs stage verified private backups before replacing a note."""
from dataclasses import asdict
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from api.db import SummaryData, TranscriptData
from summarizer import Summary, KeyPoint
from scripts import repair_source_coverage as recovery


@pytest.mark.parametrize("failure", [None, "public", "backup", "source_changed", "note_changed", "save"])
def test_repair_preserves_sources_and_requires_verified_backup_before_replacing(monkeypatch, failure):
    monkeypatch.setattr(recovery, "TARGETS", ((138, "reported"),))
    source = TranscriptData("reported", "zh", 4800, "Complete saved discussion", [])
    original = SummaryData("reported", "Original title", "Old overview", ["原有标题"], [], [{"topic": "原有标题", "summary": "Old point", "original_quote": "", "timestamp": ""}])
    candidate = Summary("reported", "Original title", "New overview", [KeyPoint("原有标题", "Full detailed discussion", "saved discussion", "")], ["原有标题"], [])
    saved = SummaryData(**asdict(candidate))
    objects = {}
    order = []
    storage = Mock()
    storage.list.return_value = []
    def upload(path, content, **kwargs):
        order.append("backup" if path.endswith("before.json") else "stage")
        if failure == "backup": raise RuntimeError("backup unavailable")
        objects[path] = content
    storage.upload.side_effect = upload
    storage.download.side_effect = lambda path: objects[path]
    db = Mock()
    db.client.storage.get_bucket.return_value = {"public": failure == "public"}
    db.client.storage.from_.return_value = storage
    class Query:
        def __init__(self, table): self.table = table
        def check(self, column):
            # Match the deployed durable-job schema: status and episode_id
            # are JSON payload fields, not separate table columns.
            if self.table == "processing_jobs":
                assert column.split("->>")[0] in {"id", "user_id", "payload", "updated_at"}
        def select(self, columns):
            for column in columns.split(","): self.check(column)
            return self
        def eq(self, column, value): self.check(column); return self
        def in_(self, column, value): self.check(column); return self
        def execute(self): return NS(data=[{"user_id": "owner"}] if self.table == "summaries" else [])
    db.client.table.side_effect = Query
    db.get_summary.side_effect = [original, SummaryData(**{**asdict(original), "overview": "Intervening user edit"}) if failure == "note_changed" else original, saved]
    db.get_transcript.side_effect = [source, TranscriptData(**{**asdict(source), "text": "Changed source"}) if failure == "source_changed" else source]
    db.save_summary.side_effect = lambda *args, **kwargs: order.append("save") or failure != "save"
    engine = Mock()
    engine.model = "fixture"
    engine.summarize.side_effect = lambda *args, **kwargs: order.append("generate") or candidate
    with patch("api.supabase_db.SupabaseDatabase", return_value=db), patch("api.user_settings.get_user_settings", return_value={}), patch("api.llm_settings.resolve_llm_settings", return_value={}), patch("summarizer.Summarizer", return_value=engine):
        if failure:
            with pytest.raises(RuntimeError): recovery.repair()
        else:
            report = recovery.repair()
            assert report["repaired"] == 1 and report["source_unchanged"] == 1
            assert order.index("backup") < order.index("generate") < order.index("save")
            before = next(json.loads(value) for key, value in objects.items() if key.endswith("before.json"))
            assert before["summary"] == asdict(original) and before["source"] == asdict(source)
            db.save_summary.assert_called_once_with("owner", **asdict(candidate))
            assert any(key.endswith("complete.json") for key in objects)
    if failure in {"public", "backup", "source_changed", "note_changed"}:
        db.save_summary.assert_not_called()
    # The maintenance path never downloads/retranscribes or writes source rows.
    assert {call.args[0] for call in db.client.table.call_args_list} <= {"summaries", "processing_jobs"}
