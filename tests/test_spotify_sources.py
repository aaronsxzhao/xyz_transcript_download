"""Spotify shares must resolve to the same public RSS episode, never a preview."""
import json
import socket
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock, AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

import spotify_podcasts_client as spotify
from api.podcast_import import save_public_episode

ID = '08tccyLPpPurxtPPrezQGZ'
URL = 'https://open.spotify.com/episode/' + ID
TITLE = '#400 – Elon Musk: War, AI, Aliens, Politics, Physics, Video Games, and Humanity'
SHOW = 'Lex Fridman Podcast'


def page(**overrides):
    entity = dict(type='episode', id=ID, title=TITLE, subtitle=SHOW, duration=8197610,
                  releaseDate={'isoString': '2023-11-09T19:55:00Z'}, audioPreview={'url': 'https://preview.example/clip.mp3'})
    entity.update(overrides)
    return ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps({'props': {'pageProps': {'state': {'data': {'entity': entity}}}}}) + '</script>').encode()


def feed(title=TITLE, duration='02:16:37', show=SHOW, date='Thu, 09 Nov 2023 19:55:00 GMT', copies=1):
    item = f'<item><title>{title}</title><guid>episode-400</guid><pubDate>{date}</pubDate><itunes:duration>{duration}</itunes:duration><enclosure url="https://audio.example/full.mp3" type="audio/mpeg"/></item>'
    return (f'<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>{show}</title>' + item * copies + '</channel></rss>').encode()


@pytest.fixture
def public(monkeypatch):
    search = {'results': [{'collectionId': 123, 'collectionName': SHOW, 'artistName': 'Lex Fridman', 'feedUrl': 'https://feed.example/rss'}]}
    fetch = Mock(side_effect=lambda url, *args: page() if 'spotify.com' in url else json.dumps(search).encode() if 'itunes.apple.com' in url else feed())
    probe = Mock()
    monkeypatch.setattr(spotify, '_get_bytes', fetch)
    monkeypatch.setattr(spotify, '_probe_audio', probe)
    return fetch, probe, search


@pytest.mark.parametrize('suffix', ['', '?si=share&utm_source=copy-link', '/'])
def test_only_valid_episode_shares_are_accepted(suffix):
    assert spotify.spotify_episode_id(URL + suffix) == ID
    assert spotify.spotify_episode_id(URL.replace('/episode/', '/intl-en/episode/')) == ID


@pytest.mark.parametrize('url', [URL.replace('https:', 'http:'), URL.replace('open.spotify.com', 'open.spotify.com.evil.example'), URL.replace('/episode/', '/show/'), URL.replace('/episode/', '/track/'), URL.replace('open.spotify.com', 'user:secret@open.spotify.com'), URL + '/extra'])
def test_unsupported_input_does_not_fetch_anything(monkeypatch, url):
    fetch = Mock(); monkeypatch.setattr(spotify, '_get_bytes', fetch)
    with pytest.raises(spotify.SpotifySourceError, match='episode link'): spotify.resolve_spotify_episode(url)
    fetch.assert_not_called()


def test_resolves_public_audio_and_retains_canonical_rss_identity(public):
    fetch, probe, _ = public
    result = spotify.resolve_spotify_episode(URL + '?si=share')
    assert result.podcast.pid == 'apple_123'
    assert result.episode.title == TITLE
    assert result.episode.duration == 8197
    assert result.episode.audio_url == 'https://audio.example/full.mp3'
    assert result.episode.eid == spotify._stable_eid('episode-400', TITLE, result.episode.audio_url)
    probe.assert_called_once_with(result.episode.audio_url, pytest.approx(time.monotonic(), abs=46))
    assert all('preview.example' not in call.args[0] for call in fetch.call_args_list)


@pytest.mark.parametrize('xml', [feed(title='Episode 401'), feed(show='Unrelated show'), feed(duration='00:30'), feed(date='Thu, 09 Nov 2022 19:55:00 GMT'), b'<html>not RSS</html>'])
def test_mismatches_and_short_previews_are_not_accepted(public, xml):
    fetch, probe, _ = public
    fetch.side_effect = [page(), json.dumps(public[2]).encode(), xml]
    with pytest.raises(spotify.SpotifySourceError, match='No matching full episode'): spotify.resolve_spotify_episode(URL)
    probe.assert_not_called()


def test_old_episode_can_be_found_beyond_the_first_fifty_items(public):
    xml = feed().replace(b'<item>', b'<item><title>Recent episode</title><enclosure url="https://audio.example/new.mp3"/></item>' * 70 + b'<item>', 1)
    public[0].side_effect = [page(), json.dumps(public[2]).encode(), xml]
    assert spotify.resolve_spotify_episode(URL).episode.title == TITLE


def test_duplicate_rss_items_with_the_same_identity_do_not_create_ambiguity(public):
    public[0].side_effect = [page(), json.dumps(public[2]).encode(), feed(copies=2)]
    assert spotify.resolve_spotify_episode(URL).episode.title == TITLE


def test_two_different_full_recordings_require_explicit_source_choice(public):
    xml = feed(copies=2).replace(b'episode-400', b'different-guid', 1).replace(b'full.mp3', b'other.mp3', 1)
    public[0].side_effect = [page(), json.dumps(public[2]).encode(), xml]
    with pytest.raises(spotify.SpotifySourceError, match='Several public recordings'): spotify.resolve_spotify_episode(URL)


def test_missing_spotify_metadata_is_explained(public):
    public[0].side_effect = [b'<html>Sign in</html>']
    with pytest.raises(spotify.SpotifySourceError, match='Cannot read this Spotify episode'): spotify.resolve_spotify_episode(URL)


def test_feed_connection_failure_is_different_from_no_match(public):
    public[0].side_effect = [page(), json.dumps(public[2]).encode(), spotify.requests.Timeout()]
    with pytest.raises(spotify.SpotifySourceError, match='could not be read'): spotify.resolve_spotify_episode(URL)


def test_public_url_validation_blocks_private_hosts_and_redirects(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [(socket.AF_INET, 1, 6, '', ('127.0.0.1', 80))])
    get = Mock(); monkeypatch.setattr(spotify.requests, 'get', get)
    with pytest.raises(spotify.SpotifySourceError): spotify._get_bytes('http://localhost/rss', time.monotonic() + 10)
    get.assert_not_called()
    def dns(host, *args, **kwargs):
        return [(socket.AF_INET, 1, 6, '', ('127.0.0.1' if host == 'internal.example' else '8.8.8.8', 80))]
    monkeypatch.setattr(socket, 'getaddrinfo', dns)
    response = Mock(status_code=302, headers={'Location': 'http://internal.example/rss'})
    get.return_value = response
    with pytest.raises(spotify.SpotifySourceError): spotify._get_bytes('https://public.example/rss', time.monotonic() + 10)
    assert get.call_count == 1
    response.close.assert_called_once()


def test_feed_size_and_audio_content_type_are_bounded(monkeypatch):
    response = Mock(headers={}, iter_content=Mock(return_value=[b'ab', b'cd']))
    monkeypatch.setattr(spotify, '_open_public', lambda *args: response)
    with pytest.raises(spotify.SpotifySourceError, match='too large'): spotify._get_bytes('https://feed.example', time.monotonic() + 10, 3)
    response.close.assert_called_once()
    response.headers = {'Content-Type': 'text/html'}
    with pytest.raises(spotify.SpotifySourceError, match='web page'): spotify._probe_audio('https://audio.example', time.monotonic() + 10)


def test_import_reuses_existing_owned_rss_episode_and_never_overwrites_its_summary(public):
    result = spotify.resolve_spotify_episode(URL)
    db = Mock(); db.get_podcast.return_value = NS(id=7,platform='apple'); db.get_episode.return_value = NS(eid=result.episode.eid)
    assert save_public_episode(db, result).id == 7
    db.add_podcast.assert_not_called(); db.add_episode.assert_not_called(); db.save_summary.assert_not_called()
    assert db.get_podcast.return_value.platform=='apple'


def test_new_spotify_import_keeps_origin_separate_from_rss_transport(public,db_interface):
    result=spotify.resolve_spotify_episode(URL)
    podcast=save_public_episode(db_interface,result)
    assert podcast.platform=='spotify'
    assert podcast.pid=='apple_123'
    assert podcast.feed_url=='https://feed.example/rss'
    assert save_public_episode(db_interface,result).id==podcast.id
    assert len(db_interface.get_episodes_by_podcast(podcast.pid))==1
    from api.routers.processing import _episode_url_from_db_episode
    assert _episode_url_from_db_episode(db_interface.get_episode(result.episode.eid))=='apple://'+result.episode.eid


def test_import_confirms_both_records_were_saved(public):
    result = spotify.resolve_spotify_episode(URL)
    db = Mock(); db.get_podcast.side_effect = [None, NS(id=7)]; db.get_episode.side_effect = [None, NS(eid=result.episode.eid)]
    save_public_episode(db, result)
    assert db.add_podcast.call_args.kwargs == {'platform': 'spotify', 'feed_url': 'https://feed.example/rss'}
    assert db.add_episode.call_args.kwargs['eid'] == result.episode.eid
    db.get_podcast.side_effect = None; db.get_podcast.return_value = None
    with pytest.raises(RuntimeError, match='save the public podcast'): save_public_episode(db, result)


@pytest.mark.asyncio
async def test_spotify_admission_queues_without_a_network_lookup(monkeypatch):
    from api.routers import processing
    resolve = Mock(side_effect=AssertionError('Source lookup belongs in the worker'))
    monkeypatch.setattr(spotify, 'resolve_spotify_episode', resolve)
    monkeypatch.setattr(processing, 'jobs', {})
    monkeypatch.setattr(processing, '_persist_new_job', AsyncMock())
    monkeypatch.setattr(processing, '_save_jobs_to_file', Mock())
    monkeypatch.setattr(processing, '_cleanup_old_jobs', Mock())
    monkeypatch.setattr(processing, 'broadcast_status', AsyncMock())
    from api.schemas import ProcessRequest
    tasks = BackgroundTasks()
    result = await processing.process_episode(ProcessRequest(episode_url=URL), tasks, NS(id='owner'))
    assert processing.jobs[result['job_id']].source_url == URL
    assert processing.jobs[result['job_id']].user_id == 'owner'
    assert tasks.tasks[0].args[1] == URL
    resolve.assert_not_called()


@pytest.mark.asyncio
async def test_failed_spotify_import_explains_public_source_problem_without_database_writes(monkeypatch):
    from api.routers import podcasts
    from api.schemas import PodcastCreate
    db = Mock(); monkeypatch.setattr(podcasts, 'get_db', lambda owner: db)
    monkeypatch.setattr(spotify, 'resolve_spotify_episode', Mock(side_effect=spotify.SpotifySourceError('No matching full episode was found')))
    with pytest.raises(HTTPException) as caught:
        await podcasts.add_podcast(PodcastCreate(url=URL), NS(id='owner'))
    assert caught.value.status_code == 422
    assert 'No matching full episode' in caught.value.detail
    db.add_podcast.assert_not_called(); db.add_episode.assert_not_called()


@pytest.mark.asyncio
async def test_successful_import_returns_the_matched_episode_and_owned_subscription(monkeypatch, public):
    from dataclasses import asdict
    from api.routers import podcasts
    from api.schemas import PodcastCreate
    result = spotify.resolve_spotify_episode(URL)
    monkeypatch.setattr(spotify, 'resolve_spotify_episode', lambda url: result)
    record = NS(id=7, platform='spotify', **asdict(result.podcast))
    db = Mock(); db.get_podcast.return_value = record
    db.get_episode.return_value = NS(eid=result.episode.eid)
    db.get_episodes_by_podcast.return_value = [result.episode]
    db.get_summary_episode_ids.return_value = set()
    get_db = Mock(return_value=db); monkeypatch.setattr(podcasts, 'get_db', get_db)
    response = await podcasts.add_podcast(PodcastCreate(url=URL), NS(id='owner'))
    assert response.resolved_episode_id == result.episode.eid
    assert response.resolved_episode_title == TITLE
    assert response.platform == 'spotify' and response.feed_url == result.podcast.feed_url
    get_db.assert_called_once_with('owner')
    db.add_episode.assert_not_called()


def test_worker_uses_resolved_public_audio_and_expected_duration(monkeypatch, public):
    from api.routers import processing
    result = spotify.resolve_spotify_episode(URL)
    monkeypatch.setattr(spotify, 'resolve_spotify_episode', lambda url: result)
    db = Mock()
    db.get_podcast.return_value = NS(id=7)
    # An old imported record must not replace the newly resolved public URL.
    db.get_episode.return_value = NS(eid=result.episode.eid, pid=result.episode.pid, podcast_id=7, title=TITLE,
                                    description='', duration=0, pub_date='', audio_url='https://old.example/expired.mp3')
    db.get_transcript.return_value = db.get_summary.return_value = db.copy_shared_transcript.return_value = None
    get_db = Mock(return_value=db); monkeypatch.setattr(processing, 'get_db', get_db)
    statuses = Mock(); monkeypatch.setattr(processing, 'update_job_status', statuses)
    monkeypatch.setattr(processing, 'is_job_cancelled', lambda job: False)
    monkeypatch.setattr('api.user_settings.get_user_settings', lambda owner: {})
    client = Mock(); monkeypatch.setattr('xyz_client.get_client', lambda: client)
    downloader = Mock(last_error='Synthetic stop after URL verification')
    downloader.download.return_value = None
    monkeypatch.setattr('downloader.get_downloader', lambda: downloader)
    processing.process_episode_sync('job', URL, transcribe_only=True, user_id='owner')
    get_db.assert_called_once_with('owner')
    episode = downloader.download.call_args.args[0]
    assert episode.audio_url == result.episode.audio_url
    assert episode.duration == 8197
    client.get_episode_by_share_url.assert_not_called()
    assert any('Finding this Spotify episode' in str(call.args) for call in statuses.call_args_list)


def test_cancelling_during_source_lookup_does_not_import_or_download(monkeypatch, public):
    from api.routers import processing
    result = spotify.resolve_spotify_episode(URL)
    cancelled = False
    def resolve(url):
        nonlocal cancelled
        cancelled = True
        return result
    monkeypatch.setattr(spotify, 'resolve_spotify_episode', resolve)
    db = Mock(); monkeypatch.setattr(processing, 'get_db', lambda owner: db)
    monkeypatch.setattr(processing, 'is_job_cancelled', lambda job: cancelled)
    monkeypatch.setattr(processing, 'mark_job_cancelled', Mock())
    statuses = Mock(); monkeypatch.setattr(processing, 'update_job_status', statuses)
    monkeypatch.setattr('api.user_settings.get_user_settings', lambda owner: {})
    processing.process_episode_sync('job', URL, transcribe_only=True, user_id='owner')
    db.add_podcast.assert_not_called(); db.add_episode.assert_not_called()
    assert statuses.call_args.args[1] == 'cancelled'
