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
import os
import subprocess
import time


def profile_public_routes(owner: str, routes: list[tuple[str, str]]) -> list[dict]:
    """Measure the deployed stack, including its auth and database connections.

    A five-minute read probe uses the existing server signing secret. Its token
    stays in memory/stdin, never command arguments, files, logs, or reports.
    The only public requests this function can issue are GETs to fixed API paths.
    """
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        return [{"library_profile": "live_unavailable"}]
    from jose import jwt
    now = int(time.time())
    token = jwt.encode({"sub": owner, "aud": "authenticated", "role": "authenticated",
                        "iat": now, "exp": now + 300}, secret, algorithm="HS256")
    selected = [("auth", "/api/auth/me"), *[(label, path) for label, path in routes
                if label in {"podcasts", "channels", "episodes", "summary", "transcript"}]]
    reports = []
    for label, path in selected:
        result = subprocess.run([
            "curl", "--silent", "--compressed", "--max-time", "25", "--header", "@-",
            "--output", os.devnull, "--write-out", "%{json}",
            "https://aipodcastsummary.online" + path,
        ], input="Authorization: Bearer " + token + "\n", capture_output=True, text=True, timeout=30)
        try:
            metrics = json.loads(result.stdout)
        except ValueError:
            metrics = {}
        reports.append({"library_profile": "live_" + label, "status": int(metrics.get("http_code") or 0),
                        "milliseconds": round(float(metrics.get("time_total") or 0) * 1000),
                        "first_byte_ms": round(float(metrics.get("time_starttransfer") or 0) * 1000),
                        "wire_bytes": int(metrics.get("size_download") or 0)})
    return reports


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
        routes.extend([("video_note", f"/api/video-notes/tasks/{task['id']}?view=note"),
                       ("video_detail", f"/api/video-notes/tasks/{task['id']}")])

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
    reports.extend(await asyncio.to_thread(profile_public_routes, owner, routes))
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
