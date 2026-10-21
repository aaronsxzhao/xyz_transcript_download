"""Compare library UI responsiveness using synthetic data and controlled latency.

Uses 7,555 segments, 4 historical notes, mobile viewport, 4x CPU throttling,
and 150ms + 1.5Mbps simulated API transfers. No production content is copied.
"""
import argparse
import asyncio
import functools
import gzip
import json
import random
import re
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class SpaHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *_args):
        pass


def serve(directory):
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SpaHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def fixtures():
    rng = random.Random(42)
    segments = [{"start": i * 4, "end": i * 4 + 4,
                 "text": f"Line {i:05d}: " + " ".join(f"word{rng.randrange(10000)}" for _ in range(8))} for i in range(7555)]
    transcript = {"text": "Synthetic long transcript. " * 3000, "segments": segments, "duration": 30220}
    task = {"id": "bench", "status": "success", "title": "Synthetic video", "platform": "youtube", "url": "fixture://video",
            "style": "detailed", "progress": 100, "markdown": "# Main takeaways\n\nA complete synthetic video note.\n\n```python\nprint(42)\n```\n\n$x^2$\n",
            "transcript": transcript, "duration": 30220, "created_at": "2026-10-19", "thumbnail": "",
            "versions": [{"id": f"v{i}", "content": f"# Saved version {i}\n\n" + "Historical content. " * 3000,
                          "style": "detailed", "created_at": "2026-10-19"} for i in range(4)]}
    summary = {"episode_id": "bench", "title": "Synthetic episode", "overview": "A promptly readable overview.",
               "topics": ["Measured topic"], "takeaways": ["A takeaway"],
               "key_points": [{"topic": "Measured topic", "summary": "Benchmark key point", "original_quote": "", "timestamp": ""}]}
    return task, summary


async def measure(browser, origin, check_processing=False):
    task, summary = fixtures()
    context = await browser.new_context(viewport={"width": 390, "height": 844}, service_workers='block')
    page = await context.new_page()
    session = await context.new_cdp_session(page)
    await session.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    errors, requests, long_tasks = [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.add_init_script("""
        localStorage.setItem('xyz_remember_me', 'true');
        localStorage.setItem('xyz_access_token', 'synthetic-token');
        localStorage.setItem('xyz_user', JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
        window.__longTasks = [];
        new PerformanceObserver(list => window.__longTasks.push(...list.getEntries().map(e => e.duration))).observe({type:'longtask'});
        window.WebSocket = class {
          static OPEN=1; readyState=1;
          constructor() {setTimeout(() => this.onopen?.(), 10)}
          send(value) {if(JSON.parse(value).type === 'auth') setTimeout(() => this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}), 5)}
          close() {this.readyState=3}
        };
    """)
    async def api(route):
        url = urlparse(route.request.url)
        path = url.path
        requests.append(path)
        body = {}
        if path == "/api/auth/config": body = {"supabase_enabled": True}
        elif path == "/api/auth/me": body = {"id": "bench", "email": "bench@example.com", "authenticated": True}
        elif path == "/api/video-notes/tasks/bench":
            body = task
            if "view=note" in url.query:
                body = {**task, "transcript": None, "versions": [{key: value for key, value in version.items() if key != 'content'} for version in task['versions']]}
        elif path == "/api/video-notes/tasks/bench/transcript": body = {"transcript": task["transcript"]}
        elif path == "/api/video-notes/tasks/bench/retry":
            task.update(status="pending", transcript=None)
            body = {"task_id": "bench"}
        elif "/api/video-notes/tasks/bench/versions/" in path: body = next(v for v in task["versions"] if v["id"] == path.rsplit('/', 1)[-1])
        elif path == "/api/summaries/bench": body = summary
        elif path == "/api/transcripts/bench": body = {**task["transcript"], "episode_id": "bench", "language": "en"}
        elif path == "/api/jobs": body = {"jobs": []}
        elif path == "/api/video-notes/progress":
            body = {"tasks": [{key: value for key,value in task.items() if key not in {'markdown','transcript','versions'}}]}
        elif path == "/api/video-notes/tasks": body = {"tasks": []}
        data = json.dumps(body, ensure_ascii=False).encode()
        if path == "/api/video-notes/tasks/bench" and body.get("status") == "transcribing":
            # Keep the status check pending while the cached completed note is
            # visible, so clicking Transcript reliably exercises that race.
            await asyncio.sleep(0.75)
        await asyncio.sleep(0.15 + len(gzip.compress(data)) / 187500)
        await route.fulfill(body=data, content_type="application/json")
    await page.route("**/api/**", api)
    started = time.perf_counter()
    await page.goto(origin + "/videos/bench", wait_until="domcontentloaded")
    await page.get_by_text("A complete synthetic video note.", exact=True).wait_for()
    note_ms = round((time.perf_counter() - started) * 1000)
    await page.locator("article .token").first.wait_for()
    await page.locator("article .katex").first.wait_for()
    eager_transcripts = requests.count("/api/video-notes/tasks/bench/transcript")
    await page.evaluate("window.__longTasks = []")
    started = time.perf_counter()
    await page.get_by_role("button", name="Transcript", exact=True).click()
    await page.get_by_text(re.compile(r"^Line 00000:")).wait_for()
    transcript_ms = round((time.perf_counter() - started) * 1000)
    row_count = await page.get_by_text(re.compile(r"^Line \d{5}:")).count()
    virtualized = await page.get_by_role("region", name="Transcript segments").count() > 0
    if virtualized:
        region = page.get_by_role("region", name="Transcript segments")
        for _ in range(3):
            await region.evaluate("element => element.scrollTop = element.scrollHeight")
            await page.wait_for_timeout(100)
        await page.get_by_text(re.compile(r"^Line 07554:")).wait_for()
    long_tasks = await page.evaluate("window.__longTasks")
    await page.get_by_role("button", name="Note", exact=True).click()
    await page.get_by_label("Note version").select_option("v1")
    await page.get_by_role("heading", name="Saved version 1", exact=True).wait_for()
    started = time.perf_counter()
    await page.goto(origin + "/viewer/bench", wait_until="domcontentloaded")
    await page.get_by_text("A promptly readable overview.", exact=True).wait_for()
    summary_ms = round((time.perf_counter() - started) * 1000)
    if check_processing:
        # Opening the tab before completion must not cache an empty transcript.
        original_transcript = task["transcript"]
        original_markdown = task["markdown"]
        task.update(status="transcribing", markdown="", transcript=None)
        transcript_requests = requests.count("/api/video-notes/tasks/bench/transcript")
        await page.goto(origin + "/videos/bench", wait_until="domcontentloaded")
        await page.get_by_role("button", name="Transcript", exact=True).click()
        await page.wait_for_timeout(350)
        assert requests.count("/api/video-notes/tasks/bench/transcript") == transcript_requests
        task.update(status="success", markdown=original_markdown, transcript=original_transcript)
        await page.get_by_text(re.compile(r"^Line 00000:")).wait_for(timeout=15000)
        # Regeneration must replace previously cached content when it completes.
        await page.get_by_role("button", name="Regenerate", exact=True).click()
        await page.get_by_role("button", name="Regenerate", exact=True).wait_for(state="hidden")
        task.update(status="success", transcript={"text": "Fresh regenerated transcript", "segments": [], "duration": 10})
        await page.get_by_text("Fresh regenerated transcript", exact=True).wait_for(timeout=15000)
    await context.close()
    assert not errors, errors
    return {"note_visible_ms": note_ms, "podcast_summary_visible_ms": summary_ms,
            "transcript_ready_ms": transcript_ms, "transcript_dom_rows": row_count,
            "max_transcript_main_thread_block_ms": round(max(long_tasks or [0])),
            "transcript_requested_before_tab": eager_transcripts,
            "last_segment_accessible": True, "version_loading": "passed", "browser_errors": errors,
            **({"processing_completion": "passed", "regeneration_refresh": "passed"} if check_processing else {})}


async def main(args):
    from playwright.async_api import async_playwright
    servers = [serve(Path(directory).resolve()) for directory in (args.baseline_dist, args.current_dist)]
    try:
        async with async_playwright() as playwright:
            options = {"headless": True}
            if args.browser_path: options["executable_path"] = args.browser_path
            if args.browser_args: options["args"] = json.loads(Path(args.browser_args).read_text())
            results = {}
            for label, server in zip(("before", "after"), servers):
                browser = await playwright.chromium.launch(**options)
                results[label] = await measure(browser, f"http://127.0.0.1:{server.server_port}", check_processing=label == "after")
                await browser.close()
                print(json.dumps({label: results[label]}), flush=True)
            print(json.dumps(results))
            assert results["after"]["transcript_dom_rows"] < 80
            assert results["after"]["transcript_requested_before_tab"] == 0
    finally:
        for server in servers: server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dist", required=True)
    parser.add_argument("--current-dist", default="web/dist")
    parser.add_argument("--browser-path")
    parser.add_argument("--browser-args")
    asyncio.run(main(parser.parse_args()))
