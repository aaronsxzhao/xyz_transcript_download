"""Read-only API profiling against production data in an isolated process.

Authentication is overridden only on this in-process test app. The deployed app
is untouched. Emit timings/sizes only: never identities, content, or credentials.
"""
import asyncio
import contextlib
import gzip
import io
import json
import logging
import time


async def profile() -> list[dict]:
    import httpx
    from api.main import app
    from api.auth import User, get_current_user
    from api.supabase_client import get_supabase_admin_client

    database = get_supabase_admin_client()
    videos = database.table("video_tasks").select("id,user_id,channel,platform").eq("status", "success").limit(1).execute().data or []
    owners = videos or database.table("podcasts").select("user_id").limit(1).execute().data or []
    if not owners:
        return [{"library_profile": "empty"}]
    owner = owners[0]["user_id"]
    app.dependency_overrides[get_current_user] = lambda: User(id=owner, email="profile@localhost")
    podcasts = database.table("podcasts").select("pid").eq("user_id", owner).limit(1).execute().data or []
    summaries = database.table("summaries").select("episode_id").eq("user_id", owner).limit(1).execute().data or []
    routes = [("stats", "/api/stats"), ("podcasts", "/api/podcasts"),
              ("recent_summaries", "/api/summaries/recent"), ("channels", "/api/video-notes/channels"),
              ("queue", "/api/video-notes/tasks"), ("settings", "/api/settings")]
    if podcasts:
        pid = podcasts[0]["pid"]
        routes.extend([("podcast_detail", f"/api/podcasts/{pid}"), ("episodes", f"/api/podcasts/{pid}/episodes")])
    if summaries:
        eid = summaries[0]["episode_id"]
        routes.extend([("summary", f"/api/summaries/{eid}"), ("transcript", f"/api/transcripts/{eid}")])
    if videos:
        task = videos[0]
        routes.extend([("video_detail", f"/api/video-notes/tasks/{task['id']}"),
                       ("video_note", f"/api/video-notes/tasks/{task['id']}?view=note")])

    calls = []
    original = httpx.Client.send
    def read_only(client, request, *args, **kwargs):
        if request.method not in {"GET", "HEAD"}:
            raise RuntimeError("Profiling permits only database reads")
        started = time.perf_counter()
        response = original(client, request, *args, **kwargs)
        calls.append(time.perf_counter() - started)
        return response
    httpx.Client.send = read_only
    reports = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://profile", timeout=30) as client:
            for label, path in routes:
                before = len(calls)
                started = time.perf_counter()
                response = await asyncio.wait_for(client.get(path), timeout=30)
                reports.append({"library_profile": label, "status": response.status_code,
                                "milliseconds": round((time.perf_counter() - started) * 1000),
                                "database_requests": len(calls) - before,
                                "response_bytes": len(response.content), "gzip_bytes": len(gzip.compress(response.content))})
    finally:
        httpx.Client.send = original
        app.dependency_overrides.clear()
    return reports


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            reports = asyncio.run(profile())
    except Exception as error:
        reports = [{"library_profile": "failed", "error_type": type(error).__name__}]
    for report in reports:
        print(json.dumps(report))
