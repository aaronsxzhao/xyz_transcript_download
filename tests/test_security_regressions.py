"""Regression coverage for authentication, private files, and account boundaries."""
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import quote, urlparse

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/podcasts", None),
    ("get", "/api/jobs", None),
    ("get", "/api/settings", None),
    ("post", "/api/settings", {"llm_model": "other-model"}),
    ("post", "/api/cookies", {"platform": "youtube", "cookie_data": "sentinel"}),
    ("delete", "/api/cookies/youtube", None),
    ("delete", "/api/video-notes/tasks/other-task", None),
    ("delete", "/api/video-notes/channels/other-channel", None),
    ("post", "/api/video-notes/generate-json", {"url": "https://youtu.be/example"}),
    ("get", "/api/summaries/example/html", None),
])
async def test_cloud_requires_a_session(client, method, path, body):
    with patch("api.auth.USE_SUPABASE", True):
        response = await client.request(method, path, json=body)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_returns_401_for_frontend_refresh(client):
    with patch("api.auth.USE_SUPABASE", True), patch("api.auth.verify_jwt_token_async", AsyncMock(return_value=None)):
        response = await client.get("/api/podcasts", headers={"Authorization": "Bearer expired"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_accepts_the_browser_json_contract(client):
    provider = Mock()
    provider.auth.refresh_session.return_value = SimpleNamespace(
        user=SimpleNamespace(id="owner", email="owner@example.com"),
        session=SimpleNamespace(access_token="new-access", refresh_token="new-refresh"),
    )
    with patch("api.routers.auth_router.USE_SUPABASE", True), patch("api.routers.auth_router.get_supabase_client", return_value=provider):
        response = await client.post("/api/auth/refresh", json={"refresh_token": "old-refresh"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "new-access"
    provider.auth.refresh_session.assert_called_once_with("old-refresh")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/data/xyz.db", "/data/jobs.json", "/data/logs/example.log", "/data/transcripts/example.json", "/data/uploads/owner/private.mp4"])
async def test_private_data_is_not_served(client, path):
    assert (await client.get(path)).status_code == 404


@pytest.mark.asyncio
async def test_frontend_fallback_rejects_encoded_traversal(client, tmp_path):
    import os
    marker = tmp_path / "private-marker.txt"
    marker.write_text("private sentinel")
    frontend = Path(__file__).resolve().parents[1] / "web" / "dist"
    relative = os.path.relpath(marker, frontend)
    response = await client.get("/" + quote(relative, safe=""))
    assert response.status_code == 404
    assert "private sentinel" not in response.text


@pytest.mark.asyncio
async def test_images_need_a_file_specific_cloud_link(client, tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, "DATA_DIR", tmp_path)
    monkeypatch.setattr(media, "USE_SUPABASE", True)
    monkeypatch.setenv("MEDIA_SIGNING_KEY", "test-media-signing-key")
    media._signing_key.cache_clear()
    image = tmp_path / "screenshots" / "owned-task_00-01.jpg"
    image.parent.mkdir()
    image.write_bytes(b"synthetic jpeg")
    signed = media.sign_media_urls("/data/screenshots/owned-task_00-01.jpg", "owned-task")
    with patch("config.USE_SUPABASE", True):
        assert (await client.get("/data/screenshots/owned-task_00-01.jpg")).status_code == 403
        assert (await client.get(signed)).content == b"synthetic jpeg"
        assert (await client.get(signed.replace("owned-task", "other-task"))).status_code == 403
    assert media.sign_media_urls("/data/screenshots/other-task_00-01.jpg", "owned-task") == "/data/screenshots/other-task_00-01.jpg"
    assert not media.verify_media_signature(urlparse(signed).path, int(time.time()) - 1, "bad-signature")
    media._signing_key.cache_clear()


@pytest.mark.asyncio
async def test_summary_html_escapes_all_generated_fields(client, create_test_summary):
    payload = '<img src=x onerror="window.compromised=1">'
    create_test_summary({"title": payload, "overview": payload, "topics": [payload], "takeaways": [payload],
                         "key_points": [{"topic": payload, "summary": payload, "original_quote": payload, "timestamp": ""}]})
    response = await client.get("/api/summaries/test-episode-456/html")
    assert response.status_code == 200
    assert "<img" not in response.text
    assert "&lt;img" in response.text
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_supabase_delete_without_owner_never_executes_a_query():
    from api.supabase_db import SupabaseDatabase
    db = SupabaseDatabase.__new__(SupabaseDatabase)
    db.client = Mock()
    assert not db.delete_video_task("victim", None)
    assert not db.delete_video_channel("victim-channel", None)
    assert not db.delete_video_channel("__unknown__", None)
    db.client.table.assert_not_called()


def test_sqlite_failed_delete_preserves_another_users_versions(tmp_path):
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(tmp_path / "video.db")
    task = db.create_task({"user_id": "owner-a", "url": "fixture://video"})
    db.add_version(task, "Private version")
    assert not db.delete_task(task, "owner-b")
    assert db.get_task(task, "owner-a")
    assert len(db.get_versions(task)) == 1


def test_cloud_cookies_are_scoped_and_do_not_fall_back_to_shared_storage():
    import cookie_manager
    provider = Mock()
    query = Mock()
    provider.table.return_value = query
    for name in ("select", "eq", "maybe_single", "upsert", "delete"):
        getattr(query, name).return_value = query
    query.execute.return_value = SimpleNamespace(data={"cookie_data": "private cookie"})
    with patch.object(cookie_manager, "USE_SUPABASE", True), patch("api.supabase_client.get_supabase_admin_client", return_value=provider):
        manager = cookie_manager.get_cookie_manager("owner-a")
        assert manager.get_cookie("youtube") == "private cookie"
        query.eq.assert_any_call("user_id", "owner-a")
        provider.table.assert_called_with("user_platform_cookies")
        manager.set_cookie("youtube", "new cookie")
        assert query.upsert.call_args.args[0]["user_id"] == "owner-a"
        assert query.upsert.call_args.kwargs["on_conflict"] == "user_id,platform"
        anonymous = cookie_manager.get_cookie_manager()
        assert anonymous.get_cookie("youtube") == ""
        with pytest.raises(PermissionError):
            anonymous.set_cookie("youtube", "bad")
    with patch.object(cookie_manager, "USE_SUPABASE", True), patch("api.supabase_client.get_supabase_admin_client", return_value=None):
        with pytest.raises(RuntimeError):
            cookie_manager.get_cookie_manager("owner-a")


@pytest.mark.asyncio
async def test_qr_sessions_cannot_be_polled_by_another_account(client):
    from api.routers import cookies
    cookies._qr_sessions["private-key"] = {"user_id": "other-owner", "created_at": time.time()}
    cookies._douyin_sessions["private-token"] = {"user_id": "other-owner", "created_at": time.time()}
    try:
        assert (await client.get("/api/cookies/bilibili/qr/poll?qrcode_key=private-key")).status_code == 404
        assert (await client.get("/api/cookies/douyin/qr/poll?token=private-token")).status_code == 404
    finally:
        cookies._qr_sessions.clear()
        cookies._douyin_sessions.clear()


def test_upload_session_paths_reject_traversal():
    from api.routers.video_notes import _upload_session_dir
    from api.routers.podcasts import _audio_upload_session_dir
    for resolve in (_upload_session_dir, _audio_upload_session_dir):
        with pytest.raises(HTTPException) as caught:
            resolve("../../private")
        assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_saved_model_preferences_are_account_scoped(client):
    from api.user_settings import get_user_settings, save_user_settings
    save_user_settings("owner-a", {"llm_model": "model-a"})
    save_user_settings("owner-b", {"llm_model": "model-b"})
    assert get_user_settings("owner-a")["llm_model"] == "model-a"
    assert get_user_settings("owner-b")["llm_model"] == "model-b"


def test_cloud_notion_does_not_reuse_a_server_owners_token():
    from api.routers import notion
    with patch.object(notion, "USE_SUPABASE", True), patch.object(notion, "NOTION_API_KEY", "private-server-key"):
        with pytest.raises(HTTPException):
            notion._get_notion_key(None)
        assert notion._get_notion_key("my-key") == "my-key"


@pytest.mark.asyncio
async def test_deleting_a_missing_episode_cannot_cancel_another_users_job(client):
    from api.routers import processing
    processing.jobs["other-job"] = processing.ProcessingStatus(job_id="other-job", user_id="other-owner", episode_id="private-episode", status="transcribing")
    response = await client.delete("/api/episodes/private-episode")
    assert response.status_code == 404
    assert "other-job" not in processing.cancelled_jobs


@pytest.mark.asyncio
async def test_cloud_debug_endpoints_require_an_admin_key(client, monkeypatch):
    with patch("api.auth.USE_SUPABASE", True):
        monkeypatch.setenv("DEBUG_API_KEY", "admin-sentinel")
        assert (await client.get("/api/debug/screenshots")).status_code == 403
        assert (await client.get("/api/debug/screenshots", headers={"X-Debug-Key": "admin-sentinel"})).status_code == 200


@pytest.mark.asyncio
async def test_private_storage_image_links_survive_without_a_local_copy(client, tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, "DATA_DIR", tmp_path)
    monkeypatch.setattr(media, "USE_SUPABASE", True)
    monkeypatch.setattr(media, "SUPABASE_URL", "https://project.example")
    monkeypatch.setenv("MEDIA_SIGNING_KEY", "test-media-signing-key")
    media._signing_key.cache_clear()
    provider = Mock()
    provider.storage.from_.return_value.download.return_value = b"private remote image"
    public_url = "https://project.example/storage/v1/object/public/screenshots/owned-task_00-01.jpg"
    signed = media.sign_media_urls(public_url, "owned-task")
    with patch("config.USE_SUPABASE", True), patch("api.supabase_client.get_supabase_admin_client", return_value=provider):
        response = await client.get(signed)
    assert response.status_code == 200
    assert response.content == b"private remote image"
    provider.storage.from_.assert_called_with("screenshots")
    provider.storage.from_.return_value.download.assert_called_once_with("owned-task_00-01.jpg")
    media._signing_key.cache_clear()
