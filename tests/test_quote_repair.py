"""Reviewed quote repairs preserve notes, source text, and private rollback data."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from api.db import TranscriptData
from scripts import repair_reported_quotes as recovery


def fixture():
    source = TranscriptData('episode', 'zh', 80, '开头 句子。\n原话 在这里。', [
        {'start': 0, 'end': 5, 'text': '开头句子。'},
        {'start': 65.9, 'end': 70, 'text': '原话在这里。'}])
    rows = [{'id': 12, 'summary_id': 137, 'summary': 'Detailed claim', 'original_quote': '', 'timestamp': ''}]
    plan = {'summary_id': 137, 'episode_id': 'episode',
            'source_md5': hashlib.md5(source.text.encode()).hexdigest(),
            'segments_sha256': recovery.segment_digest(source.segments),
            'points': [{'point_sha256': hashlib.sha256(rows[0]['summary'].encode()).hexdigest(), 'segments': [1, 2]}]}
    return source, rows, plan


def test_quotes_are_exact_substrings_with_real_segment_times_and_no_body_changes():
    source, rows, plan = fixture()
    before = deepcopy((asdict(source), rows))
    updates = recovery.quote_updates(source, rows, plan)
    assert updates == [(rows[0], {'original_quote': '原话 在这里。', 'timestamp': '00:01:05'})]
    assert (asdict(source), rows) == before
    assert recovery.quote_updates(source, [{**rows[0], **updates[0][1]}], plan) == []


@pytest.mark.parametrize('change', ['text', 'segments', 'summary', 'quote', 'range', 'missing', 'duplicate'])
def test_repair_refuses_changed_sources_notes_quotes_and_invalid_ranges(change):
    source, rows, plan = fixture()
    if change == 'text': source.text += 'new source'
    if change == 'segments': source.segments[1]['start'] = 66
    if change == 'summary': rows[0]['summary'] = 'new note'
    if change == 'quote': rows[0]['original_quote'] = 'A newer selected quote'
    if change == 'range': plan['points'][0]['segments'] = [1, 3]
    if change == 'missing': rows.clear()
    if change == 'duplicate': rows.append(dict(rows[0]))
    with pytest.raises(RuntimeError): recovery.quote_updates(source, rows, plan)


@pytest.mark.parametrize('failure', [None, 'public', 'backup', 'source_changed', 'conflict'])
def test_private_backup_precedes_guarded_quote_only_updates(monkeypatch, failure):
    source, rows, plan = fixture()
    original = {'id': 137, 'episode_id': 'episode', 'user_id': 'owner', 'overview': 'Unchanged overview'}
    order, objects = [], {}
    storage = Mock()
    def upload(path, content, **kwargs):
        order.append('backup' if path.endswith('before.json') else 'receipt')
        if failure == 'backup': raise RuntimeError('Backup unavailable')
        objects[path] = content
    storage.upload.side_effect = upload
    storage.download.side_effect = lambda path: objects[path]
    db = Mock()
    db.client.storage.get_bucket.return_value = {'public': failure == 'public'}
    db.client.storage.from_.return_value = storage
    db.get_transcript.side_effect = [source, TranscriptData(**{**asdict(source), 'text': 'Changed'}) if failure == 'source_changed' else source, source]
    class Query:
        def __init__(self, table): self.table, self.patch, self.filters = table, None, {}
        def select(self, fields): return self
        def eq(self, key, value): self.filters[key] = value; return self
        def is_(self, key, value): self.filters[key] = None; return self
        def in_(self, *args): return self
        def update(self, values): self.patch = values; return self
        def execute(self):
            if self.table == 'summaries': return NS(data=[dict(original)])
            if self.table == 'processing_jobs': return NS(data=[])
            assert self.table == 'summary_key_points'
            if self.patch:
                assert set(self.patch) == {'original_quote', 'timestamp'}
                assert self.filters == {key: rows[0][key] for key in ('id', 'summary_id', 'summary', 'original_quote', 'timestamp')}
                order.append('update')
                if failure == 'conflict': return NS(data=[])
                rows[0].update(self.patch)
            return NS(data=deepcopy(rows))
    db.client.table.side_effect = Query
    monkeypatch.setattr(recovery.Path, 'read_text', lambda *args: json.dumps([plan]))
    with patch('api.supabase_db.SupabaseDatabase', return_value=db):
        if failure:
            with pytest.raises(RuntimeError): recovery.repair()
        else:
            assert recovery.repair() == {'operation': 'restore_verbatim_quotes', 'repaired': 1, 'already_repaired': 0}
            assert order == ['backup', 'update', 'receipt']
            before = json.loads(next(value for key, value in objects.items() if key.endswith('before.json')))
            assert before['key_points'][0]['original_quote'] == ''
            assert before['source'] == asdict(source)
            assert before['summary'] == original
    if failure in {'public', 'backup', 'source_changed'}:
        assert 'update' not in order
