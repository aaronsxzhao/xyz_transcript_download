"""Source failures must not look like empty feeds or successful subscriptions."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import apple_podcasts_client
import xyz_client


@pytest.mark.asyncio
@pytest.mark.parametrize('platform',['apple','spotify'])
async def test_rss_without_feed_never_falls_back_to_xiaoyuzhou(client,db_interface,monkeypatch,platform):
    db_interface.add_podcast('missing-feed','Missing feed',platform=platform)
    xyz=Mock();monkeypatch.setattr(xyz_client,'get_client',xyz)
    response=await client.post('/api/podcasts/missing-feed/refresh')
    assert response.status_code==422
    assert 'RSS' in response.json()['detail']
    xyz.assert_not_called()


@pytest.fixture(params=["xiaoyuzhou", "apple", "spotify"])
def source(request, monkeypatch):
    platform = request.param
    podcast = SimpleNamespace(
        pid="source-test", title="Source test", author="Author", description="Description",
        cover_url="", feed_url="https://example.com/feed.xml",
    )
    episode = SimpleNamespace(
        eid="source-episode", pid=podcast.pid, title="Episode", description="",
        duration=60, pub_date="2026-10-23", audio_url="https://example.com/audio.mp3",
    )
    network = Mock(side_effect=requests.Timeout("source timeout"))
    if platform in ("apple", "spotify"):
        monkeypatch.setattr(apple_podcasts_client, "get_podcast_by_url", lambda _: podcast)
        monkeypatch.setattr(apple_podcasts_client.requests, "get", network)
        url = "https://podcasts.apple.com/podcast/id123456"
        body = b'<rss><channel><item><title>Episode</title><guid>source-episode</guid><enclosure url="https://example.com/audio.mp3"/></item></channel></rss>'
        empty = b"<rss><channel/></rss>"
    else:
        client = xyz_client.XyzClient.__new__(xyz_client.XyzClient)
        client.session = SimpleNamespace(get=network)
        client.get_podcast_by_url = lambda _: podcast
        client.get_episode_by_share_url = lambda _: episode
        client.get_user_subscriptions = lambda _: [podcast]
        client.extract_user_id = lambda _: "profile"
        monkeypatch.setattr(xyz_client, "get_client", lambda: client)
        url = "https://www.xiaoyuzhoufm.com/podcast/source-test"
        body = b'<html><a href="/episode/0123456789abcdef01234567">Episode</a></html>'
        empty = b"<html></html>"
    return SimpleNamespace(platform=platform, podcast=podcast, network=network, url=url, body=body, empty=empty)


def respond(source, body=None):
    source.network.side_effect = None
    source.network.return_value = SimpleNamespace(
        content=source.body if body is None else body, raise_for_status=lambda: None,
    )


@pytest.mark.asyncio
async def test_failed_subscription_leaves_no_empty_subscription_and_can_retry(client, db_interface, source):
    failed = await client.post("/api/podcasts", json={"url": source.url})
    assert failed.status_code == 502
    assert db_interface.get_podcast(source.podcast.pid) is None
    respond(source)
    retried = await client.post("/api/podcasts", json={"url": source.url})
    assert retried.status_code == 200
    assert retried.json()["episode_count"] == 1
    assert len(db_interface.get_episodes_by_podcast(source.podcast.pid)) == 1


@pytest.mark.asyncio
async def test_failed_refresh_reports_source_error_and_preserves_existing_episodes(
    client, db_interface, create_test_episode, source,
):
    podcast_id = db_interface.add_podcast(source.podcast.pid, "Source", platform=source.platform, feed_url=source.podcast.feed_url)
    create_test_episode(podcast_id=podcast_id, override={"pid": source.podcast.pid})
    response = await client.post(f"/api/podcasts/{source.podcast.pid}/refresh")
    assert response.status_code == 502
    assert "retry" in response.json()["detail"].lower()
    assert len(db_interface.get_episodes_by_podcast(source.podcast.pid)) == 1


@pytest.mark.asyncio
async def test_genuinely_empty_source_is_still_a_valid_subscription(client, source):
    respond(source, source.empty)
    response = await client.post("/api/podcasts", json={"url": source.url})
    assert response.status_code == 200
    assert response.json()["episode_count"] == 0


@pytest.mark.asyncio
async def test_subscription_conflict_does_not_save_episodes_without_a_parent(client, db_interface, source, monkeypatch):
    from api.routers import podcasts
    respond(source)
    monkeypatch.setattr(podcasts, "get_db", lambda _: db_interface)
    monkeypatch.setattr(db_interface, "add_podcast", lambda *a, **kw: None)
    save_episode = Mock()
    monkeypatch.setattr(db_interface, "add_episode", save_episode)
    response = await client.post("/api/podcasts", json={"url": source.url})
    assert response.status_code == 409
    save_episode.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["xiaoyuzhou"], indirect=True)
async def test_failed_bulk_import_can_be_retried_instead_of_skipping_an_empty_subscription(client, db_interface, source):
    failed = await client.post("/api/podcasts/import-subscriptions", json={"username": "profile"})
    assert failed.status_code == 200
    assert failed.json()["failed"] == 1
    assert failed.json()["newly_added"] == 0
    assert db_interface.get_podcast(source.podcast.pid) is None
    respond(source)
    retried = await client.post("/api/podcasts/import-subscriptions", json={"username": "profile"})
    assert retried.status_code == 200
    assert retried.json()["newly_added"] == 1
    assert retried.json()["already_subscribed"] == 0
    assert len(db_interface.get_episodes_by_podcast(source.podcast.pid)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"<broken", b"<html>upstream error</html>"])
async def test_invalid_rss_is_not_saved_as_an_empty_apple_subscription(client, db_interface, monkeypatch, body):
    podcast = SimpleNamespace(pid="invalid-feed", title="Invalid", author="", description="", cover_url="", feed_url="https://example.com/feed")
    monkeypatch.setattr(apple_podcasts_client, "get_podcast_by_url", lambda _: podcast)
    monkeypatch.setattr(apple_podcasts_client.requests, "get", lambda *a, **kw: SimpleNamespace(content=body, raise_for_status=lambda: None))
    response = await client.post("/api/podcasts", json={"url": "https://podcasts.apple.com/podcast/id123456"})
    assert response.status_code == 502
    assert db_interface.get_podcast(podcast.pid) is None
