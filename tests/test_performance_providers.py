"""Guard request responsiveness, provider routing, and complete summary outputs."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


@pytest.mark.asyncio
async def test_slow_video_database_does_not_block_health(client):
    from api.routers import video_notes
    started, release = threading.Event(), threading.Event()
    database = Mock()
    def slow_query(*args):
        started.set()
        assert release.wait(3)
        return []
    database.list_tasks.side_effect = slow_query
    video_notes._list_cache.clear()
    with patch("video_task_db.get_video_task_db", return_value=database):
        pending = asyncio.create_task(client.get("/api/video-notes/tasks"))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            response = await asyncio.wait_for(client.get("/api/health"), 0.5)
            assert response.status_code == 200
        finally:
            release.set()
            assert (await pending).status_code == 200
            video_notes._list_cache.clear()


def test_summary_metadata_is_batched_and_owner_scoped():
    from api.supabase_db import SupabaseDatabase
    database = SupabaseDatabase.__new__(SupabaseDatabase)
    database.client = Mock()
    query = database.client.table.return_value
    query.select.return_value = query.eq.return_value = query.in_.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{
        "eid": "episode-a", "podcasts": {"title": "My podcast", "cover_url": "cover"},
    }])
    result = database.get_summary_podcast_metadata("owner", ["episode-a", "episode-b"])
    assert result == {"episode-a": ("My podcast", "cover")}
    assert query.eq.call_args_list == [(('user_id', 'owner'),), (('podcasts.user_id', 'owner'),)]
    query.in_.assert_called_once_with("eid", ["episode-a", "episode-b"])
    query.execute.assert_called_once()


def test_legacy_jwt_verification_needs_no_jwks_network():
    from jose import jwt
    import api.auth as auth
    token = jwt.encode({"sub": "owner", "aud": "authenticated", "exp": 4102444800}, "secret", algorithm="HS256")
    with patch.object(auth, "USE_SUPABASE", True), patch.object(auth, "SUPABASE_JWT_SECRET", "secret"), patch.object(auth, "_fetch_jwks") as fetch:
        assert auth.verify_jwt_token(token)["sub"] == "owner"
    fetch.assert_not_called()


def test_empty_jwks_is_cached_and_force_refresh_is_bounded():
    import api.auth as auth
    cache = {"keys": None, "fetched_at": 0, "attempted_at": 0, "lock": threading.Lock()}
    with patch.object(auth, "_jwks_cache", cache), patch.object(auth, "_fetch_jwks", return_value={"keys": []}) as fetch:
        for _ in range(5):
            assert auth._get_cached_jwks(force_refresh=True) == {"keys": []}
        fetch.assert_called_once()


def test_groq_preferences_use_existing_key_and_ignore_stale_gateway_models():
    import api.llm_settings as providers
    with patch.object(providers, "GROQ_API_KEY", "existing-private-key"):
        settings = providers.resolve_llm_settings({"llm_provider": "groq"}, "vertex_ai/old-model")
        assert settings == {"api_key": "existing-private-key", "base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"}
        assert "existing-private-key" not in str(providers.provider_status({"llm_provider": "groq"}))


def test_saving_one_preference_preserves_provider_and_other_models():
    from api.user_settings import get_user_settings, save_user_settings
    save_user_settings("provider-owner", {"llm_provider": "groq", "llm_model": "openai/gpt-oss-20b", "whisper_model": "whisper-large-v3"})
    save_user_settings("provider-owner", {"whisper_model": "whisper-large-v3-turbo"})
    result = get_user_settings("provider-owner")
    assert result["llm_provider"] == "groq"
    assert result["llm_model"] == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_existing_groq_key_is_used_by_default_without_exposing_credentials(client):
    import api.llm_settings as providers
    with patch.object(providers, "GROQ_API_KEY", "private-paid-groq-key"):
        result = await client.get("/api/settings")
    assert result.status_code == 200
    assert result.json()["llm_provider"] == "groq"
    assert result.json()["llm_model"] == "openai/gpt-oss-120b"
    assert "private-paid-groq-key" not in result.text


def test_unsupported_vision_mode_fails_clearly_instead_of_leaving_task_pending():
    from video_task_db import get_video_task_db
    from api.routers.video_notes import process_video_note_sync
    database = get_video_task_db()
    task_id = database.create_task({"user_id": "local", "url": "fixture://vision"})
    with patch("api.llm_settings.resolve_llm_settings", return_value={"model": "openai/gpt-oss-120b", "api_key": "fixture", "base_url": "https://api.groq.com/openai/v1"}):
        process_video_note_sync(task_id, "fixture://vision", "youtube", "detailed", ["summary"], "medium", "", "", True, 4, 3, 3, "local")
    result = database.get_task(task_id, "local")
    assert result["status"] == "failed"
    assert "Turn off Video Understanding" in result["error"]


@pytest.mark.asyncio
async def test_connection_test_returns_useful_errors_without_secrets(client):
    error = RuntimeError("private-key secret endpoint")
    error.status_code = 429
    with patch("api.llm_settings.test_summary_connection", side_effect=error):
        result = await client.post("/api/settings/test-llm", json={"llm_provider": "groq", "llm_model": "openai/gpt-oss-120b"})
    assert result.status_code == 502
    assert "quota" in result.json()["detail"]
    assert "private-key" not in result.text


def test_groq_long_podcast_chunks_fit_and_failed_chunk_preserves_prior_summary():
    from summarizer import Summarizer
    from transcriber import Transcript
    summarizer = Summarizer(api_key="fixture", base_url="https://api.groq.com/openai/v1", model="openai/gpt-oss-120b")
    transcript = Transcript(episode_id="episode", language="zh", duration=100, text="中文内容。" * 15000, segments=[])
    with patch.object(summarizer, "_summarize_single", return_value=None) as single:
        assert summarizer.summarize(transcript) is None
        assert 10000 < len(single.call_args.args[1]) <= 30000


def test_groq_video_chunks_fail_instead_of_saving_partial_notes():
    from note_summarizer import NoteSummarizer
    summarizer = NoteSummarizer(api_key="fixture", base_url="https://api.groq.com/openai/v1", model="openai/gpt-oss-120b")
    text = "一段中文内容。" * 4000
    chunks = summarizer._split_transcript(text)
    assert "".join(chunks) == text
    assert max(map(len, chunks)) <= 10000
    with patch.object(summarizer, "_call_llm", side_effect=["First part", RuntimeError("quota exceeded")]):
        with pytest.raises(RuntimeError):
            summarizer.generate_note("Title", text)


@pytest.mark.asyncio
async def test_assets_cache_immutably_but_html_revalidates(client):
    import re
    html = await client.get("/")
    assert html.headers["cache-control"].startswith("public, max-age=60")
    assert "set-cookie" not in html.headers
    unchanged = await client.get("/", headers={"If-None-Match": html.headers["etag"]})
    assert unchanged.status_code == 304 and not unchanged.content
    path = re.search(r'src="(/assets/[^"<>]+\.js)"', html.text).group(1)
    asset = await client.get(path)
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
