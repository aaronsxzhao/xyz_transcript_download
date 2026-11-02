import threading
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from processing_execution import Execution, bind


@pytest.mark.parametrize('platform', ['youtube', 'douyin'])
@pytest.mark.parametrize('outcome', ['success', 'cancel', 'quality_blocked'])
def test_visual_preparation_overlaps_transcription_and_joins_before_summary(monkeypatch, tmp_path, platform, outcome):
    cancel = outcome == 'cancel'
    from api.routers import video_notes as routes
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(tmp_path / 'video.db')
    ident = db.create_task({'url': 'https://www.youtube.com/watch?v=example', 'platform': platform, 'user_id': 'owner'})
    monkeypatch.setattr('video_task_db.get_video_task_db', lambda: db)
    monkeypatch.setattr(routes, '_broadcast_from_thread', Mock())
    monkeypatch.setattr('api.user_settings.get_user_settings', lambda owner: {})
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings', lambda *args: {'api_key': 'test', 'base_url': 'https://model.example', 'model': 'test'})
    monkeypatch.setattr('cookie_manager.get_cookie_manager', lambda owner: Mock(get_cookie=lambda platform: None))
    primary, secondary = Mock(), Mock()
    primary.get_metadata.return_value = SimpleNamespace(title='Title', thumbnail='cover.jpg', duration=120, tags=[], channel='', channel_url='', channel_avatar='', published_at='')
    primary.get_subtitles.return_value = []
    audio_downloaded = threading.Event()
    def audio(*args, **kwargs):
        audio_downloaded.set()
        return tmp_path / 'audio.mp3'
    primary.download_audio.side_effect = audio
    primary.get_last_download_info.return_value = None
    media = secondary if platform == 'youtube' else primary
    def download_video(*args, **kwargs):
        if platform != 'youtube':
            assert audio_downloaded.is_set(), 'Shared video must not race audio extraction'
        return tmp_path / 'video.mp4'
    media.download_video.side_effect = download_video
    factory = Mock(side_effect=[primary, secondary] if platform == 'youtube' else [primary])
    monkeypatch.setattr('video_downloader.normalize_video_url', lambda url, platform: url)
    monkeypatch.setattr('video_downloader.get_downloader', factory)
    vision_started, transcribed = threading.Event(), threading.Event()
    monkeypatch.setattr('video_understanding.extract_frame_grids', lambda *args, **kwargs: ['grid.jpg'])
    def vision(*args, **kwargs):
        vision_started.set()
        assert transcribed.wait(3), 'Vision ran after transcription rather than overlapping it'
        return 'Visual evidence'
    monkeypatch.setattr('video_understanding.analyze_grids', vision)
    def transcribe(*args, **kwargs):
        assert vision_started.wait(3), 'Video preparation was not started before transcription'
        transcribed.set()
        if cancel:
            raise routes.VideoCancelledException('Cancelled during transcription')
        return SimpleNamespace(text='Complete source with supporting details. ' * 10, segments=[])
    monkeypatch.setattr('transcriber.get_transcriber', lambda **kwargs: Mock(transcribe=transcribe))
    summarizer = Mock()
    def summary(**kwargs):
        assert transcribed.is_set() and kwargs['visual_context'] == 'Visual evidence'
        if outcome == 'quality_blocked':
            from summary_errors import SummaryOutputError
            raise SummaryOutputError('quality')
        return '# Complete notes\n\nGrounded content.'
    summarizer.generate_note.side_effect = summary
    monkeypatch.setattr('note_summarizer.get_note_summarizer', lambda **kwargs: summarizer)
    with bind(Execution('owner', 'source', Mock())):
        routes.process_video_note_sync(ident, 'https://www.youtube.com/watch?v=example', platform, 'detailed', ['summary'], 'medium', '', '', True, 4, 3, 3, 'owner')
    result = db.get_task(ident, 'owner')
    expected = {'success':'success', 'cancel':'cancelled', 'quality_blocked':'failed'}[outcome]
    assert result['status'] == expected, result['message']
    if outcome == 'quality_blocked':
        assert not result.get('markdown')
        assert 'quality threshold' in result['error']
    if cancel:
        summarizer.generate_note.assert_not_called()
    assert factory.call_count == (2 if platform == 'youtube' else 1)
    if platform == 'youtube':
        primary.download_video.assert_not_called()
        secondary.download_audio.assert_not_called()
    else:
        primary.download_video.assert_called_once()


def test_visual_frame_cache_is_scoped_to_source_file(monkeypatch, tmp_path):
    import video_understanding as vision
    first, second = tmp_path / 'first.mp4', tmp_path / 'second.mp4'
    first.write_bytes(b'first'); second.write_bytes(b'second')
    monkeypatch.setattr(vision, 'GRIDS_DIR', tmp_path / 'grids')
    monkeypatch.setattr('screenshot_extractor.get_video_duration', lambda path: 1)
    def capture(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_bytes(Path(command[command.index('-i')+1]).read_bytes())
    monkeypatch.setattr('resource_scheduler.run_media_process', capture)
    a, b = vision.extract_frames(str(first)), vision.extract_frames(str(second))
    assert a[0][1] != b[0][1]
    assert a[0][1].read_bytes() == b'first' and b[0][1].read_bytes() == b'second'
