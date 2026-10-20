"""Exercise full page loading with synthetic data and delayed network responses.

    Models a slow path: 400ms per asset, 6s session verification, 2s data reads.
    Warm revisits use 8s background reads to prove cached content stays usable.
    Reports synthetic measurements only, never production content/credentials.
"""
import argparse
import asyncio
import base64
import functools
import json
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.frontend import frontend_html


class Preview(SimpleHTTPRequestHandler):
    def __init__(self, *args, bootstrap=False, **kwargs):
        self.bootstrap = bootstrap
        super().__init__(*args, **kwargs)

    def do_GET(self):
        file = Path(self.translate_path(self.path))
        if file.is_file() and file.name != "index.html":
            return super().do_GET()
        root = Path(self.directory)
        html = frontend_html(root, urlparse(self.path).path.lstrip('/'), True, "https://example.supabase.co") if self.bootstrap else (root / "index.html").read_text()
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


def token(exp):
    encoded = base64.urlsafe_b64encode(json.dumps({"sub": "bench", "exp": exp}).encode()).decode().rstrip('=')
    return "e30." + encoded + ".synthetic-signature"


async def check_release_navigation(context, origin, api, asset, state, asset_failures):
    state.update(revoked=False, delay=.05)
    page = await context.new_page()
    await page.route('**/api/**', api)
    await page.route('**/assets/**', asset)
    await page.goto(origin + '/podcasts', wait_until='domcontentloaded')
    await page.get_by_text('小宇宙', exact=True).first.wait_for()
    manifest = await (await context.request.get(origin+'/manifest.json')).json()
    if not manifest.get('src/pages/Settings.tsx', {}).get('isDynamicEntry'):
        # With all page controllers bundled, denied route chunks must not be
        # needed for Settings at all. Entry replacement is checked separately.
        asset_failures['mode'] = 'always'
        await page.evaluate("history.pushState({},'','/settings');dispatchEvent(new PopStateEvent('popstate'))")
        await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=5000)
        assert asset_failures['count'] == 0
        await page.close()
        return {'deployment_navigation':'passed','route_chunk_not_required':'passed'}
    asset_failures['mode'] = 'once'
    async with page.expect_navigation(wait_until='domcontentloaded', timeout=10000):
        await page.evaluate("history.pushState({},'','/settings');dispatchEvent(new PopStateEvent('popstate'))")
    await page.get_by_role('heading', name='Settings', exact=True).wait_for()
    assert asset_failures['count'] == 1
    # A continuing outage gets a usable error screen instead of reloads.
    await page.goto(origin + '/podcasts', wait_until='domcontentloaded')
    await page.get_by_text('小宇宙', exact=True).first.wait_for()
    asset_failures['mode'] = 'always'
    await page.evaluate("history.pushState({},'','/settings');dispatchEvent(new PopStateEvent('popstate'))")
    await page.get_by_role('button', name='Reload page', exact=True).wait_for()
    await page.wait_for_timeout(500)
    assert await page.get_by_role('button', name='Reload page', exact=True).is_visible()
    await page.close()
    return {"deployment_navigation": "passed", "persistent_asset_error": "passed"}


async def measure(browser, origin, verify, recovery_only=False):
    context = await browser.new_context(viewport={"width": 390, "height": 844}, service_workers='block')
    fresh_token = token(int(time.time()) + 3600)
    await context.add_init_script("""
        localStorage.setItem('xyz_remember_me','true');
        if(!localStorage.getItem('xyz_access_token')) {
          localStorage.setItem('xyz_access_token',TOKEN);
          localStorage.setItem('xyz_refresh_token','synthetic-refresh');
          localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
        }
        window.WebSocket=class {static OPEN=1;readyState=1;
          constructor(){setTimeout(()=>this.onopen?.(),10)}
          send(value){if(JSON.parse(value).type==='auth')setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),5)}
          close(){this.readyState=3}
        };
    """.replace('TOKEN', json.dumps(fresh_token)))
    page = await context.new_page()
    session = await context.new_cdp_session(page)
    await session.send('Emulation.setCPUThrottlingRate', {"rate": 4})
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    state = {"delay": 2, "revoked": False, "summary_missing": False, "summary_unavailable": False, "settings_error": False}
    asset_failures = {'mode': '', 'count': 0}
    podcast = {"pid": "bench", "title": "Synthetic podcast", "author": "Author", "description": "Description",
               "cover_url": "", "episode_count": 1, "summarized_count": 1, "platform": "xiaoyuzhou", "feed_url": ""}
    episode = {"eid": "bench", "pid": "bench", "title": "Synthetic episode", "description": "Description",
               "duration": 30, "pub_date": "2026-10-19", "created_at": "2026-10-19", "cover_url": "", "audio_url": "",
               "status": "summarized", "has_transcript": True, "has_summary": True, "topics_count": 1, "key_points_count": 0}
    summary = {"episode_id": "bench", "title": "Synthetic episode", "overview": "Readable saved overview.",
               "topics": ["Topic"], "takeaways": [], "key_points": []}

    async def api(route):
        path = urlparse(route.request.url).path
        authorization = route.request.headers.get('authorization', '')
        requests.append((path, authorization))
        body, status = {}, 200
        delay = state['delay']
        public = path == '/api/auth/config'
        if public:
            body = {"supabase_enabled": True, "supabase_url": "https://example.supabase.co"}
        elif path == '/api/auth/refresh':
            status = 401 if state['revoked'] else 200
            body = {"access_token": fresh_token, "refresh_token": "synthetic-next", "user_id": "bench", "email": "bench@example.com"}
        elif path == '/api/auth/me':
            delay = 6
            body = {"id": "bench", "email": "bench@example.com", "authenticated": True}
        elif path == '/api/podcasts': body = [podcast]
        elif path == '/api/podcasts/bench': body = podcast
        elif path == '/api/podcasts/bench/episodes': body = [episode]
        elif path == '/api/video-notes/channels':
            body = {"channels": [{"channel": "Synthetic channel", "platform": "youtube", "channel_url": "", "channel_avatar": "", "thumbnail": "", "total": 1, "done": 1, "last_updated": ""}]}
        elif path.startswith('/api/summaries/'):
            body = summary
            if state['summary_missing']: status = 404
            if state['summary_unavailable']:
                status, body = 503, {'detail': 'Temporary summary connection failure'}
        elif path == '/api/settings':
            body = {"whisper_mode": "api", "whisper_model": "whisper-large-v3", "llm_provider": "groq",
                    "llm_model": "openai/gpt-oss-120b", "groq_available": True, "check_interval": 3600}
            if state['settings_error']: status, body = 503, {'detail': 'Temporary settings connection failure'}
        elif path.startswith('/api/transcripts/'):
            body = {"episode_id": "bench", "language": "en", "text": "Full transcript on demand.", "duration": 30, "segments": []}
        elif path == '/api/jobs': body = {"jobs": []}
        elif path == '/api/video-notes/tasks': body = {"tasks": []}
        if state['revoked'] and not public: status = 401
        await asyncio.sleep(delay)
        try:
            await route.fulfill(status=status, body=json.dumps(body), content_type='application/json')
        except Exception:
            pass  # Navigation may cancel background verification/read requests.

    async def asset(route):
        await asyncio.sleep(.4)
        if '/Settings-' in route.request.url and asset_failures['mode']:
            asset_failures['count'] += 1
            if asset_failures['mode'] == 'once': asset_failures['mode'] = ''
            return await route.fulfill(status=404, body='Page file replaced', content_type='text/plain')
        await route.continue_()

    await page.route('**/api/**', api)
    await page.route('**/assets/**', asset)
    if recovery_only:
        result = await check_release_navigation(context, origin, api, asset, state, asset_failures)
        await context.close()
        return result
    paths = [('/podcasts', '小宇宙'), ('/videos', '1/1 completed'),
             ('/podcasts/bench/episodes', 'Synthetic episode'), ('/viewer/bench', 'Readable saved overview.')]
    cold, warm = {}, {}
    for path, text in paths:
        started = time.perf_counter()
        await page.goto(origin + path, wait_until='domcontentloaded')
        await page.get_by_text(text, exact=True).first.wait_for(timeout=25000)
        label = 'episodes' if path.endswith('/episodes') else path.split('/')[1]
        cold[label] = round((time.perf_counter() - started) * 1000)
    transcript_reads = sum(path.startswith('/api/transcripts/') for path, _ in requests)
    if verify:
        assert transcript_reads == 0, 'Summary opening downloaded an unrequested transcript'
        await page.get_by_role('button', name='Transcript', exact=True).click()
        await page.get_by_text('Full transcript on demand.', exact=True).wait_for()
    state['delay'] = 8
    for path, text in paths:
        started = time.perf_counter()
        await page.evaluate("path => {history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))}", path)
        await page.get_by_text(text, exact=True).first.wait_for(timeout=20000)
        label = 'episodes' if path.endswith('/episodes') else path.split('/')[1]
        warm[label] = round((time.perf_counter() - started) * 1000)
    if verify:
        assert max(warm.values()) < 2000, warm
        state['delay'] = .2
        await page.evaluate("localStorage.removeItem('xyz_cache_bench:summary_bench');history.pushState({},'','/podcasts/bench/episodes');dispatchEvent(new PopStateEvent('popstate'))")
        await page.get_by_role('link', name='View', exact=True).focus()
        await page.wait_for_function("localStorage.getItem('xyz_cache_bench:summary_bench') !== null")
        state['delay'] = 8
        prefetch_started = time.perf_counter()
        await page.get_by_role('link', name='View', exact=True).click()
        await page.get_by_text('Readable saved overview.', exact=True).wait_for(timeout=1500)
        prefetched_summary_ms = round((time.perf_counter() - prefetch_started) * 1000)
        assert prefetched_summary_ms < 1500
        await page.evaluate("history.pushState({},'','/settings');dispatchEvent(new PopStateEvent('popstate'))")
        await page.get_by_role('heading', name='Settings', exact=True).wait_for(timeout=2000)
        await page.get_by_role('button', name='Platform Accounts', exact=True).click()
        assert await page.get_by_role('button', name='General', exact=True).is_enabled()
        await page.get_by_role('button', name='General', exact=True).click()
        # Finish this deliberately slow request before testing a separate failed
        # refresh; overlapping reads correctly share the pending request.
        await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]')?.disabled")
        state['delay'] = .2
        state['summary_unavailable'] = True
        await page.evaluate("history.pushState({},'','/viewer/unavailable');dispatchEvent(new PopStateEvent('popstate'))")
        await page.get_by_text('Temporary summary connection failure', exact=True).wait_for()
        assert not any(path == '/api/transcripts/unavailable' for path, _ in requests), 'A server failure must not trigger a second, unrelated content request'
        assert await page.get_by_text('Process this episode to generate transcript and summary', exact=True).count() == 0
        state['summary_unavailable'] = False
        state['settings_error'] = True
        await page.evaluate("history.pushState({},'','/settings');dispatchEvent(new PopStateEvent('popstate'))")
        await page.get_by_text('Temporary settings connection failure', exact=True).wait_for()
        state['settings_error'] = False
        await page.get_by_role('button', name='Retry', exact=True).click()
        await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]')?.disabled")
        state['summary_missing'] = True
        await page.evaluate("history.pushState({},'','/viewer/transcript-only');dispatchEvent(new PopStateEvent('popstate'))")
        await page.get_by_text('Full transcript on demand.', exact=True).wait_for()
        assert await page.get_by_role('button', name='Transcript', exact=True).count() == 1
        state['summary_missing'] = False
        expired = token(int(time.time()) - 60)
        await page.evaluate("value => localStorage.setItem('xyz_access_token', value)", expired)
        request_count = len(requests)
        await page.goto(origin + '/podcasts', wait_until='domcontentloaded')
        await page.get_by_text('小宇宙', exact=True).first.wait_for()
        await page.wait_for_timeout(1500)
        assert sum(path == '/api/auth/refresh' for path, _ in requests[request_count:]) == 1
        assert not any(auth == 'Bearer ' + expired for _, auth in requests[request_count:])
        state['revoked'] = True
        await page.goto(origin + '/podcasts', wait_until='domcontentloaded')
        await page.wait_for_url('**/login', timeout=12000)
        await page.wait_for_timeout(2500)
        assert urlparse(page.url).path == '/login', 'Late session response restored a revoked account'
        await check_release_navigation(context, origin, api, asset, state, asset_failures)
    assert not errors, errors
    await context.close()
    return {"cold_ms": cold, "revisit_ms": warm, "eager_transcript_reads": transcript_reads,
            **({"prefetched_summary_ms": prefetched_summary_ms} if verify else {}),
            **({"lazy_transcript": "passed", "transcript_only": "passed", "expired_session": "passed", "revoked_session": "passed"} if verify else {})}


async def main(args):
    from playwright.async_api import async_playwright
    servers = []
    try:
        async with async_playwright() as playwright:
            for label, directory in [('before', args.baseline_dist), ('after', args.current_dist)]:
                if args.recovery_only and label == 'before': continue
                server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Preview, directory=str(Path(directory).resolve()), bootstrap=label == 'after'))
                threading.Thread(target=server.serve_forever, daemon=True).start()
                servers.append(server)
                options = {"headless": True}
                if args.browser_path: options['executable_path'] = args.browser_path
                if args.browser_args: options['args'] = json.loads(Path(args.browser_args).read_text())
                browser = await playwright.chromium.launch(**options)
                result = await measure(browser, f'http://127.0.0.1:{server.server_port}', verify=label == 'after', recovery_only=args.recovery_only)
                await browser.close()
                print(json.dumps({label: result}), flush=True)
    finally:
        for server in servers: server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-dist', required=True)
    parser.add_argument('--current-dist', default='web/dist')
    parser.add_argument('--browser-path')
    parser.add_argument('--browser-args')
    parser.add_argument('--recovery-only', action='store_true')
    asyncio.run(main(parser.parse_args()))
