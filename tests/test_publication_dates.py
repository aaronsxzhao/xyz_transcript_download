from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from publication_dates import publication_date


@pytest.mark.parametrize('info,expected', [
    ({'upload_date': '20241025'}, '2024-10-25'),
    ({'release_date': '20241024', 'upload_date': '20241025'}, '2024-10-24'),
    ({'timestamp': 1729814400}, '2024-10-25'),
    ({'release_timestamp': '1729814400'}, '2024-10-25'),
    ({'epoch': 1729814400}, ''),
    ({'upload_date': '20240230', 'timestamp': 1729814400}, '2024-10-25'),
    ({'upload_date': '2024-10-25'}, '2024-10-25'),
    ({'upload_date': 20241025, 'timestamp': 'invalid'}, ''),
    ({'timestamp': float('inf')}, ''),
])
def test_only_actual_source_dates_are_accepted(info, expected):
    assert publication_date(info) == expected


def test_download_metadata_recovers_date_when_upload_date_missing():
    from video_downloader import YtdlpDownloader
    downloader = YtdlpDownloader('youtube')
    downloader._last_info = {'title': 'Video', 'timestamp': 1729814400}
    assert downloader.get_last_download_info().published_at == '2024-10-25'


def test_share_page_reads_date_after_separate_podcast_script():
    from xyz_client import XyzClient
    html = '''<meta property="og:title" content="Episode">
    <meta property="og:audio" content="https://example.com/audio.mp3">
    <script type="application/json">{"podcast":{"pid":"p"}}</script>
    <script type="application/json">{"episode":{"pid":"p","duration":600,"pubDate":"2024-10-25T00:00:00Z"}}</script>'''
    response = Mock(status_code=200, content=html.encode())
    client = XyzClient()
    # Public scraping does not need an authenticated source account.
    with patch.object(client.session, 'get', return_value=response):
        episode = client.get_episode_by_share_url('https://www.xiaoyuzhoufm.com/episode/test')
    assert episode.pub_date == '2024-10-25T00:00:00Z'
    assert episode.duration == 600


def test_repair_only_fills_missing_owner_dates_and_verifies_real_sdk_query():
    import json
    import httpx
    from postgrest import SyncPostgrestClient
    from scripts.repair_publication_dates import repair
    rows = [dict(id='v', user_id='owner', platform='youtube', url='https://youtube.com/watch?v=test', published_at=None)]
    patches = []
    def handle(request):
        if request.method == 'PATCH':
            assert request.url.params['id'] == 'eq.v'
            assert request.url.params['user_id'] == 'eq.owner'
            assert request.url.params['published_at'] == 'is.null'
            fields = json.loads(request.content)
            assert fields == {'published_at': '2024-10-25'}
            rows[0].update(fields); patches.append(fields)
            return httpx.Response(200, json=rows)
        if request.url.params.get('select') == 'published_at':
            assert request.url.params['user_id'] == 'eq.owner'
            return httpx.Response(200, json=[{'published_at': rows[0]['published_at']}])
        assert request.url.params['or'] == '(published_at.is.null,published_at.eq.)'
        return httpx.Response(200, json=rows if rows[0]['published_at'] is None else [])
    client = SyncPostgrestClient('https://fixture.test/rest/v1')
    client.session = httpx.Client(transport=httpx.MockTransport(handle))
    report = repair(client, lambda task: '2024-10-25')
    assert report['repaired'] == report['verified'] == 1
    assert len(patches) == 1
    assert repair(client, lambda task: pytest.fail('Already dated content must not be fetched'))['examined'] == 0


def test_processing_preserves_date_from_audio_download(tmp_path):
    from video_task_db import get_video_task_db
    from video_downloader import VideoMetadata
    from api.routers import video_notes
    db = get_video_task_db()
    task_id = db.create_task({'user_id': 'local', 'platform': 'youtube', 'url': 'https://youtube.com/watch?v=test'})
    downloader = Mock()
    downloader.get_metadata.return_value = None
    downloader.get_subtitles.return_value = None
    downloader.download_audio.return_value = tmp_path / 'audio.mp3'
    downloader.get_last_download_info.return_value = VideoMetadata(title='Video', duration=60, published_at='2024-10-25')
    engine = Mock()
    engine.transcribe.return_value = None  # Stop after metadata, before any LLM work.
    with patch('video_downloader.get_downloader', return_value=downloader), \
         patch('cookie_manager.get_cookie_manager') as cookies, \
         patch('transcriber.get_transcriber', return_value=engine), \
         patch('api.llm_settings.resolve_llm_settings', return_value={'model': 'synthetic', 'base_url': 'https://example.com', 'api_key': 'synthetic'}), \
         patch('api.user_settings.get_user_settings', return_value={}):
        cookies.return_value.get_cookie.return_value = ''
        video_notes.process_video_note_sync(task_id, 'https://youtube.com/watch?v=test', 'youtube', 'detailed', ['summary'], 'medium', '', '', False, 4, 3, 3, 'local')
    assert db.get_task(task_id, 'local')['published_at'] == '2024-10-25'


def test_library_reads_only_visible_owner_date_metadata_and_keeps_saved_order():
    import httpx
    from postgrest import SyncPostgrestClient
    from api.routers.library import page_rows
    requests = []
    def handle(request):
        requests.append(request)
        assert request.url.params['user_id'] == 'eq.owner'
        assert request.url.params['limit'] == '2'
        assert request.url.params['select'] in ('eid,pub_date,pid', 'id,published_at')
        if request.url.path.endswith('/episodes'):
            assert request.url.params['eid'] == 'in.(p)'
            return httpx.Response(200, json=[{'eid': 'p', 'pid': 'source', 'pub_date': '2024-10-25'}])
        assert request.url.params['id'] == 'in.(v)'
        return httpx.Response(200, json=[{'id': 'v', 'published_at': '2023-01-01'}])
    client = SyncPostgrestClient('https://fixture.test/rest/v1')
    client.session = httpx.Client(transport=httpx.MockTransport(handle))
    rows = [dict(id='p', kind='podcast', date='2026-10-21', sort_key='3'),
            dict(id='v', kind='video', date='2026-10-20', sort_key='2'),
            dict(id='off-page', kind='video', date='2026-10-19', sort_key='1')]
    result = page_rows(rows, 2, SimpleNamespace(db=SimpleNamespace(client=client)), 'owner')
    assert len(requests) == 2
    assert [r['published_at'] for r in result['items']] == ['2024-10-25', '2023-01-01']
    assert [r['date'] for r in result['items']] == ['2026-10-21', '2026-10-20']
    assert result['next_cursor'] == '2'


def test_date_repair_does_not_call_a_player_when_watch_page_provides_date():
    from scripts.repair_publication_dates import source_date
    html = b'<meta itemprop="datePublished" content="2024-10-25T10:00:00Z">'
    with patch('requests.get', return_value=Mock(content=html)), \
         patch('cookie_manager.get_cookie_manager') as cookies, \
         patch('video_downloader.get_downloader'), \
         patch('yt_dlp.YoutubeDL') as extractor:
        cookies.return_value.get_cookie.return_value = ''
        assert source_date({'platform': 'youtube', 'url': 'https://www.youtube.com/watch?v=test', 'user_id': 'owner'}) == '2024-10-25'
        extractor.assert_not_called()
