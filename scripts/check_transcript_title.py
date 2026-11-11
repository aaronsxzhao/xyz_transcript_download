"""Isolated production-build regression for transcript-only reader titles.

Run after npm --prefix web run build. No production requests or credentials.
"""
import argparse
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass
    def log_message(self, *_):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'appearance-checks/transcript-title')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(AppHandler, directory=str(ROOT/'web/dist')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    result = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', chromium_sandbox=True, headless=True)
            context = browser.new_context(ignore_https_errors=False, service_workers='block')
            metadata = {'fail': False}
            held = []
            def api(route):
                path = urlsplit(route.request.url).path
                status, body = 200, {}
                if path == '/api/auth/config': body = {'supabase_enabled': False}
                elif path == '/api/auth/me': body = {'id': 'local', 'email': '', 'authenticated': True}
                elif path == '/api/jobs': body = {'jobs': []}
                elif path.startswith('/api/summaries/'):
                    status, body = 404, {'detail': 'Summary not found'}
                elif path.startswith('/api/transcripts/'):
                    eid = path.rsplit('/', 1)[1]
                    body = {'episode_id': eid, 'language': 'en', 'duration': 60, 'text': 'Retained transcript content.', 'segments': [{'start': 0, 'end': 60, 'text': 'Retained transcript content.'}]}
                elif path.startswith('/api/episodes/'):
                    eid = path.rsplit('/', 1)[1]
                    if eid == 'late':
                        held.append(route)
                        return
                    if metadata['fail']: status, body = 503, {'detail': 'Metadata unavailable'}
                    else: body = {'eid': eid, 'title': 'Long episode title / 保留转写的分集标题 '+eid}
                route.fulfill(status=status, content_type='application/json', body=json.dumps(body))
            context.route('**/api/**', api)
            page = context.new_page()
            origin = f'http://127.0.0.1:{server.server_port}'
            for design, color, width, height in [('classic','dark',1440,900),('classic','light',768,1024),('editorial','light',390,844),('editorial','dark',390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                page.goto(origin+'/viewer/first')
                expect(page.get_by_role('heading', level=1)).to_have_text('Long episode title / 保留转写的分集标题 first')
                expect(page.locator('#podcast-transcript')).to_contain_text('Retained transcript content.')
                page.get_by_label('Interface style').select_option(design)
                if page.locator('html').get_attribute('data-theme') != color:
                    page.get_by_role('button',name='Switch to '+color+' mode',exact=True).click()
                expect(page.locator('html')).to_have_attribute('data-theme',color)
                page.wait_for_timeout(400)
                page.reload()
                expect(page.get_by_role('heading', level=1)).to_have_text('Long episode title / 保留转写的分集标题 first')
                expect(page.locator('#podcast-transcript')).to_contain_text('Retained transcript content.')
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                page.wait_for_timeout(400)
                page.screenshot(path=str(args.output/f'{design}-{color}-{width}.png'))
                result.append({'case':f'{design}-{color}-{width}-reload','passed':True})
            metadata['fail'] = True
            page.goto(origin+'/viewer/second')
            expect(page.locator('#podcast-transcript')).to_contain_text('Retained transcript content.')
            expect(page.get_by_role('heading', level=1)).to_have_text('Episode Viewer')
            result.append({'case':'metadata failure leaves transcript readable without prior episode title','passed':True})
            metadata['fail'] = False
            page.goto(origin+'/viewer/late')
            expect(page.locator('#podcast-transcript')).to_contain_text('Retained transcript content.')
            page.wait_for_timeout(100)
            assert held
            page.evaluate("history.pushState({}, '', '/viewer/current');dispatchEvent(new PopStateEvent('popstate'))")
            expect(page.get_by_role('heading', level=1)).to_have_text('Long episode title / 保留转写的分集标题 current')
            for route in held:
                route.fulfill(content_type='application/json', body=json.dumps({'eid':'late','title':'Stale title must not appear'}))
            page.wait_for_timeout(300)
            expect(page.get_by_role('heading', level=1)).to_have_text('Long episode title / 保留转写的分集标题 current')
            result.append({'case':'late metadata cannot overwrite a different episode','passed':True})
            browser.close()
    finally:
        server.shutdown()
    (args.output/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__ == '__main__': main()
