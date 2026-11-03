"""Read-only API profiling against production data in an isolated process.

Authentication uses a scoped platform test token. Emit timings/sizes only: never identities, content, or credentials.
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


def restricted_summary_route(database, owner):
    """A historical fixture is optional; ordinary current routes remain required."""
    episode = '6ad08b370e4e410a05bd4fd0'
    rows = (database.table('episode_source_access').select('eid').eq('user_id', owner)
            .eq('eid', episode).eq('status', 'purchase_required').limit(1).execute().data or [])
    if not rows:
        return None
    saved = (database.table('summaries').select('episode_id').eq('user_id', owner)
             .eq('episode_id', episode).limit(1).execute().data or [])
    return '/api/summaries/' + episode if saved else None


def profile_public_routes(owner: str, routes: list[tuple[str, str]], local_video: str | None = None) -> list[dict]:
    """Read deployed routes with a provisioned diagnostic token, never a signed JWT."""
    token = os.environ.get("PLATFORM_TEST_TOKEN", "").strip()
    if not token:
        return [{"library_profile": "live_unavailable"}]
    selected = [("auth", "/api/stats"), *[(label, path) for label, path in routes
                if label in {"restricted_summary", "content_updates", "progress", "podcasts", "channels", "episodes", "summary", "transcript", "settings", "channel_videos", "podcast_index", "reported_episodes", "reported_episode_failure", "reported_summary", "reported_video_note", "reported_latest_summary", "completed_local_video"}]]
    reports = []
    # Inspect the running app's inventory, rather than this isolated process.
    # Source links, titles and credentials never enter diagnostic output.
    inventory = subprocess.run([
        'curl','--fail','--silent','--compressed','--max-time','20',
        '--max-filesize','1048576','--header','@-',
        'https://aipodcastsummary.online/api/jobs',
    ],input='Authorization: Bearer '+token+'\n',capture_output=True,text=True,timeout=25)
    try:
        jobs=json.loads(inventory.stdout)['jobs']
        if inventory.returncode or not isinstance(jobs,list): raise ValueError()
        active=[job for job in jobs if job.get('status') not in ('completed','failed','cancelled')]
        reports.append({'library_profile':'live_processing_admission','status':200,
                        'waiting_jobs':sum(job.get('status')=='pending' for job in active),
                        'active_jobs':len(active),
                        'jobs_without_source':sum(not job.get('source_url') for job in active)})
    except (ValueError,KeyError,TypeError):
        reports.append({'library_profile':'live_processing_admission','status':0})
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
    return reports


def settings_key_status(data: dict) -> dict:
    """Only public presence/error flags leave the diagnostic process."""
    result = {}
    for prefix in ('llm', 'whisper'):
        result[prefix + '_key_saved'] = int(data.get(prefix + '_key_saved') is True)
        result[prefix + '_key_error'] = int(bool(data.get(prefix + '_key_error')))
    return result


if __name__ == "__main__":
    from scripts.platform_diagnostics import run
    raise SystemExit(0 if run() else 1)
