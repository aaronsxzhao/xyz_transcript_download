"""Saved transcripts survive expired media links and optional screenshot errors."""
import json
from unittest.mock import Mock

import pytest

from content_sources import ContentDocument, saved_web_media
from social_content import SocialSourceError


@pytest.fixture
def media_worker(monkeypatch, tmp_path):
    from api.routers import video_notes as routes
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(tmp_path / 'retry.db')
    source = ContentDocument('web', 'https://media.example/recording.mp4', 'Saved title',
        'Original description and attribution.', author='Original author',
        thumbnail='https://media.example/cover.jpg', content_type='video',
        media=[{'url': 'https://media.example/recording.mp4', 'kind': 'video', 'duration': 120}])
    ident = db.create_task({'url': source.url, 'platform': 'web', 'user_id': 'owner'})
    text = 'Complete original English transcript, with all its conditions. ' * 10
    db.update_task(ident, {'title': source.title, 'thumbnail': source.thumbnail,
        'channel': source.author, 'duration': 120, 'source_metadata': source.metadata(),
        'transcript_json': json.dumps({'text': text, 'segments': [], 'duration': 120})})
    monkeypatch.setattr('video_task_db.get_video_task_db', lambda: db)
    monkeypatch.setattr(routes, '_broadcast_from_thread', Mock())
    monkeypatch.setattr(routes, 'start_task', Mock())
    monkeypatch.setattr('api.user_settings.get_user_settings', lambda owner: {})
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings', lambda *a: {
        'api_key': 'test', 'base_url': 'https://model.example', 'model': 'selected-model'})
    resolve = Mock(side_effect=SocialSourceError('The original media has expired'))
    monkeypatch.setattr('content_sources.resolve_content', resolve)
    download = Mock()
    monkeypatch.setattr('social_downloader.SocialDownloader', lambda source: download)
    summarizer = Mock()
    summarizer.generate_note.return_value = '# Structured result\n\nAll substantive details.'
    monkeypatch.setattr('note_summarizer.get_note_summarizer', lambda **kw: summarizer)
    def run(formats):
        routes.process_video_note_sync(ident, source.url, 'web', 'detailed', formats,
            'medium', '', '', False, 4, 3, 3, 'owner')
        return db.get_task(ident, 'owner')
    return db, ident, run, resolve, download, summarizer, text


def test_regeneration_reuses_full_transcript_and_source_without_network(media_worker):
    db, ident, run, resolve, download, summarizer, text = media_worker
    result = run(['summary'])
    assert result['status'] == 'success', result['message']
    assert summarizer.generate_note.call_args.kwargs['transcript_text'] == text
    assert 'Original description and attribution.' in result['markdown']
    assert result['title'] == 'Saved title' and result['channel'] == 'Original author'
    resolve.assert_not_called()
    download.download_audio.assert_not_called()
    download.download_video.assert_not_called()
    assert len(db.get_versions(ident)) == 1


def test_optional_screenshot_failure_keeps_generated_text_and_reports_warning(media_worker):
    _, _, run, resolve, download, summarizer, text = media_worker
    download.download_video.side_effect = SocialSourceError('Source no longer available')
    result = run(['summary', 'screenshot'])
    assert result['status'] == 'success', result['message']
    assert 'All substantive details.' in result['markdown']
    assert 'screenshots need attention' in result['message']
    assert summarizer.generate_note.call_args.kwargs['transcript_text'] == text
    resolve.assert_not_called()


def test_optional_screenshot_cancellation_is_not_treated_as_success(media_worker):
    from api.routers.video_notes import VideoCancelledException
    _, _, run, _, download, summarizer, _ = media_worker
    download.download_video.side_effect = VideoCancelledException('Cancelled')
    result = run(['summary', 'screenshot'])
    assert result['status'] == 'cancelled'
    summarizer.generate_note.assert_not_called()


def test_legacy_direct_media_can_regenerate_but_articles_and_empty_transcripts_refetch(media_worker):
    db, ident, _, _, _, _, _ = media_worker
    task = db.get_task(ident, 'owner')
    task['source_metadata'].pop('media')
    task['source_metadata'].pop('source_body')
    restored = saved_web_media(task)
    assert restored.media[0]['url'] == task['url']
    assert '[Original media]' in restored.body
    task['source_metadata']['type'] = 'article'
    assert saved_web_media(task) is None
    task['source_metadata']['type'] = 'video'
    task['transcript']['text'] = ''
    assert saved_web_media(task) is None


def test_invalid_saved_media_does_not_bypass_public_url_validation(media_worker):
    db, ident, _, _, _, _, _ = media_worker
    task = db.get_task(ident, 'owner')
    task['source_metadata']['media'][0]['url'] = 'http://127.0.0.1/private'
    assert saved_web_media(task) is None


def test_missing_thumbnail_does_not_force_a_download_when_regenerating(media_worker):
    db, ident, run, resolve, download, _, _ = media_worker
    db.update_task(ident, {'thumbnail': ''})
    result = run(['summary'])
    assert result['status'] == 'success'
    resolve.assert_not_called()
    download.download_video.assert_not_called()


def test_stream_updates_are_throttled_but_cancellation_is_checked_on_every_block(media_worker, monkeypatch):
    from api.routers import video_notes as routes
    _, _, run, _, download, summarizer, _ = media_worker
    updates = Mock(wraps=routes._update_task_status)
    monkeypatch.setattr(routes, '_update_task_status', updates)
    cancelled = [False]
    monkeypatch.setattr(routes, 'is_video_task_cancelled', lambda ident: cancelled[0])
    def stream(*args, progress_callback, **kwargs):
        for _ in range(100):
            progress_callback(.1, 'Streaming media')
        cancelled[0] = True
        progress_callback(.2, 'Streaming media')
        raise AssertionError('Cancellation was ignored')
    download.download_video.side_effect = stream
    result = run(['summary', 'screenshot'])
    assert result['status'] == 'cancelled'
    assert sum(call.args[4] == 'Streaming media' for call in updates.call_args_list if len(call.args) > 4) == 1
    summarizer.generate_note.assert_not_called()
