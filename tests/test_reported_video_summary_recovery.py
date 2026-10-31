from unittest.mock import Mock, patch
import pytest
from scripts import repair_reported_video_summary as recovery


def database(rows):
    client = Mock()
    query = client.table.return_value
    query.select.return_value.eq.return_value.ilike.return_value.gte.return_value.execute.return_value.data = rows
    return client


def row():
    return {'id': 'task', 'user_id': 'owner', 'title': '斯坦福大学：如何创业 第1讲 - 如何开始创业'}


@pytest.mark.parametrize('rows', [[], [row(), row()]])
def test_recovery_refuses_missing_or_ambiguous_reported_task(rows):
    with patch('api.supabase_client.get_supabase_admin_client', return_value=database(rows)), patch.object(recovery, 'request_json') as request:
        with pytest.raises(RuntimeError):
            recovery.repair({'SUPABASE_JWT_SECRET': 'fixture'})
    request.assert_not_called()


def test_recovery_retries_only_target_and_verifies_saved_transcript(monkeypatch):
    monkeypatch.setenv('EXPECTED_REVISION', 'release')
    failed = {'status': 'failed', 'transcript': {'text': 'Original'}}
    saved = dict(failed, status='success', markdown='Saved notes', versions=[{'id': 'v1'}])
    with patch('api.supabase_client.get_supabase_admin_client', return_value=database([row()])), patch.object(recovery, 'request_json', side_effect=[{'revision': 'release'}, failed, {}, saved]) as request:
        result = recovery.repair({'SUPABASE_JWT_SECRET': 'fixture'})
    assert result['status'] == 'verified'
    assert result['transcript_preserved']
    assert request.call_args_list[2].args[0] == '/api/video-notes/tasks/task/retry'
