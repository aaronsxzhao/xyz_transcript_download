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


def profile_public_routes(owner: str, routes: list[tuple[str, str]], local_video: str | None = None) -> list[dict]:
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
                if label in {"progress", "podcasts", "channels", "episodes", "summary", "transcript", "settings", "channel_videos", "reported_episodes", "reported_episode_failure", "reported_summary", "reported_video_note", "reported_latest_summary", "completed_local_video"}]]
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
    # Optional until the new release is live. Only this owner's bounded numeric
    # browser measurements are returned, never URLs or page contents.
    observed = subprocess.run([
        "curl", "--silent", "--compressed", "--max-time", "15", "--max-filesize", "16384",
        "--header", "@-", "--write-out", "\n%{http_code}",
        "https://aipodcastsummary.online/api/performance",
    ], input="Authorization: Bearer " + token + "\n", capture_output=True, text=True, timeout=20)
    body, _, status = observed.stdout.rpartition("\n")
    if status == "200":
        try:
            pages = json.loads(body).get("pages", {})
        except ValueError:
            pages = {}
        for label in {"dashboard", "podcasts", "videos", "channel", "episodes", "viewer", "video_note", "settings"} & pages.keys():
            row = pages[label]
            safe = {"library_profile": "browser_" + label}
            for source, target in {"elapsed_ms": "milliseconds", "first_paint_ms": "first_paint_ms", "document_ms": "document_ms",
                                   "api_ms": "api_ms", "server_ms": "server_ms", "samples": "samples", "cached": "cached",
                                   "worst_ms": "worst_ms", "error_count": "error_count", "slow_count": "slow_count", "program_embedded": "program_embedded", "module_requests": "module_requests", "module_failures": "module_failures", "script_errors": "script_errors"}.items():
                if isinstance(row.get(source), int) and 0 <= row[source] <= 300000:
                    safe[target] = int(row[source])
            safe["bootstrap"] = int(row.get("stage") == "bootstrap")
            reports.append(safe)
    from scripts.profile_cover_sources import profile_covers
    reports.extend(profile_covers(owner))
    if os.environ.get('XYZ_PROFILE_BROWSER') == '1':
        from scripts.profile_live_browser import profile_browser
        reports.extend(asyncio.run(profile_browser(owner, token, local_video)))
    return reports


async def profile() -> list[dict]:
    import httpx
    from api.main import app
    from api.auth import User, get_current_user
    from api.supabase_client import get_supabase_admin_client

    database = get_supabase_admin_client()
    videos = database.table("video_tasks").select("id,user_id,channel,platform").eq("id", "bc2c988b-2b4").eq("status", "success").limit(1).execute().data or []
    if not videos:
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
              ("queue", "/api/video-notes/tasks"), ("progress", "/api/video-notes/progress"), ("settings", "/api/settings")]
    if podcasts:
        pid = podcasts[0]["pid"]
        routes.extend([("podcast_detail", f"/api/podcasts/{pid}"), ("episodes", f"/api/podcasts/{pid}/episodes")])
        # These reported failures belong to this podcast owner. Check ownership
        # before probing; diagnostics must never read another account's data.
        reported = database.table("podcasts").select("pid").eq("user_id", owner).eq("pid", "62382c1103bea1ebfffa1c00").execute().data or []
        if reported:
            routes.extend([
                ("reported_episodes", "/api/podcasts/62382c1103bea1ebfffa1c00/episodes"),
                ("reported_summary", "/api/summaries/694b7d6d0b60b7bf752e007b"),
                ("channel_videos", "/api/video-notes/tasks/by-channel?platform=youtube&channel=Brooks+Trading+Course"),
                ("reported_video_note", "/api/video-notes/tasks/bc2c988b-2b4?view=note"),
            ])
    routes.append(("reported_episode_failure", "/api/podcasts/6540c81e9cb67569a2f99856/episodes?offset=0&limit=50"))
    if summaries:
        eid = summaries[0]["episode_id"]
        routes.extend([("summary", f"/api/summaries/{eid}"), ("transcript", f"/api/transcripts/{eid}")])
    if videos:
        task = videos[0]
        routes.extend([("video_note", f"/api/video-notes/tasks/{task['id']}?view=note"),
                       ("video_detail", f"/api/video-notes/tasks/{task['id']}")])

    latest = database.table("summaries").select("episode_id").eq("user_id", owner).eq("episode_id", "699acfb5de29766da924dee1").limit(1).execute().data or []
    if latest:
        routes.append(("reported_latest_summary", "/api/summaries/699acfb5de29766da924dee1"))
    local = database.table("video_tasks").select("id").eq("user_id", owner).eq("platform", "local").eq("status", "success").limit(1).execute().data or []
    local_video = local[0]["id"] if local else None
    if local_video:
        routes.append(("completed_local_video", f"/api/video-notes/tasks/{local_video}?view=note"))

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
    reports.extend(await asyncio.to_thread(profile_public_routes, owner, routes, local_video))
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
