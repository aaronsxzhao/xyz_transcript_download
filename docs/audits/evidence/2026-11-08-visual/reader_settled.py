"""Read-only cloud Chromium smoke checks; screenshots require separate human review."""
import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

VIEWPORTS = [(1440, 900), (768, 1024), (390, 844)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://aipodcastsummary.online')
    parser.add_argument('--browser-path', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('appearance-checks/cloud-browser'))
    parser.add_argument('--authenticated', action='store_true',
                        help='Sign in through UI using optional environment bindings or a no-echo terminal prompt')
    args = parser.parse_args()
    origin = args.origin.rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or parsed.netloc == '' or parsed.username or parsed.query or parsed.fragment or parsed.path:
        parser.error('--origin must be an HTTP(S) origin without credentials, path or query')
    email, password = os.environ.get('BROWSER_TEST_EMAIL'), os.environ.get('BROWSER_TEST_PASSWORD')
    if args.authenticated and not (email and password):
        if not sys.stdin.isatty():
            parser.error('Use a private interactive terminal or secure runtime bindings; never pass credentials as CLI arguments')
        email = email or getpass.getpass('Authorized test email (hidden): ')
        password = password or getpass.getpass('Authorized test password (hidden): ')
        if not (email and password):
            parser.error('Authorized test credentials are empty')
    if (args.output / 'results.json').exists():
        parser.error('Use a fresh --output directory so evidence from previous runs cannot be mixed')
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'origin': origin,
              'mode': 'authenticated' if args.authenticated else 'anonymous',
              'authenticated_session_verified': False, 'visual_inspection': 'NOT_REVIEWED',
              'sandbox_enabled': True, 'tls_verification': True, 'checks': [],
              'blocked_write_requests': 0}
    stage = 'launch'
    page = None
    screenshot_allowed = False
    try:
        with sync_playwright() as playwright:
            options = dict(executable_path=args.browser_path, headless=True, chromium_sandbox=True,
                           ignore_default_args=['--disable-client-side-phishing-detection',
                                                '--disable-ipc-flooding-protection',
                                                '--unsafely-disable-devtools-self-xss-warnings',
                                                '--enable-unsafe-swiftshader'])
            proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            if proxy:
                options['proxy'] = {'server': proxy}
            browser = playwright.chromium.launch(**options)
            report['browser_version'] = browser.version
            context = browser.new_context(ignore_https_errors=False, service_workers='block')
            login_allowed = args.authenticated

            def guard(route):
                request = route.request
                target = urlsplit(request.url)
                if target.path == '/api/performance' and target.netloc == parsed.netloc:
                    return route.fulfill(status=204)
                if request.method in ('GET', 'HEAD', 'OPTIONS'):
                    return route.continue_()
                if login_allowed and request.method == 'POST' and request.url == origin + '/api/auth/signin':
                    return route.continue_()
                report['blocked_write_requests'] += 1
                route.abort()

            context.route('**/*', guard)
            page = context.new_page()
            page.set_default_timeout(20000)
            if args.authenticated:
                stage = 'authentication'
                page.goto(origin + '/login', wait_until='networkidle')
                page.get_by_label('Email', exact=True).fill(email)
                page.get_by_label('Password', exact=True).fill(password)
                with page.expect_response(lambda r: r.url == origin + '/api/auth/signin') as pending:
                    page.get_by_role('button', name='Sign In', exact=True).click()
                response = pending.value
                assert response.status == 200, 'Login rejected'
                # Inspect only a boolean; never persist token, response body or storage state.
                assert bool(response.json().get('access_token')), 'No session issued'
                login_allowed = False
                page.wait_for_url(lambda url: urlsplit(str(url)).path != '/login')
                with page.expect_response(lambda r: urlsplit(r.url).path == '/api/stats') as pending:
                    page.goto(origin + '/', wait_until='networkidle')
                assert pending.value.status == 200, 'Protected API rejected session'
                report['authenticated_session_verified'] = True
            screenshot_allowed = True
            stage='application'
            results=[]
            def record(name, **kwargs):
                results.append(dict(name=name,**kwargs))
                (args.output/'exploration.json').write_text(json.dumps(results,indent=2))
            def shot(name,mask=False):
                page.screenshot(path=str(args.output/(name+'.png')),mask=[page.locator('input'),page.locator('textarea')] if mask else [])
            def prose():
                return page.locator('article[data-rendering="formatted"]').evaluate("e=>{const c=e.cloneNode(true);c.querySelectorAll('.screenshot-block,.screenshot-caption,.reader-screenshot,.summary-screenshot-placeholder,button,[role=status],img').forEach(x=>x.remove());return c.textContent.replace(/\\s+/g,' ').trim()}")
            page.set_viewport_size({'width':1440,'height':900})
            page.goto(origin+'/library',wait_until='domcontentloaded')
            expect(page.get_by_role('button',name='Refresh library',exact=True)).to_be_enabled(timeout=60000)
            page.locator('a.library-card').first.click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            expect(page.locator('article .katex').first).to_be_attached(timeout=20000)
            initial_captions=page.locator('article .screenshot-caption').evaluate_all('(xs)=>({count:xs.length,chars:xs.reduce((n,x)=>n+x.textContent.length,0)})')
            before=prose()
            page.get_by_role('tab',name='Transcript',exact=True).click()
            expect(page.locator('#video-transcript')).to_be_visible()
            page.get_by_role('tab',name='Summary',exact=True).click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible()
            with page.expect_response(lambda r: urlsplit(r.url).path.startswith('/api/video-notes/tasks/') and len(urlsplit(r.url).path.strip('/').split('/'))==4 and r.status==200):
                page.reload(wait_until='domcontentloaded')
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            expect(page.locator('article .katex').first).to_be_attached(timeout=20000)
            after=prose()
            page.locator('article .katex').first.scroll_into_view_if_needed()
            shot('currency-math-rendering')
            record('reader-roundtrip',same_prose=before==after,before_chars=len(before),after_chars=len(after),protected_response=200,initial_captions=initial_captions)
            assert before==after, 'Semantic prose differs after excluding both image wrappers and error statuses'
            shot('reader-refresh')
            page.go_back(wait_until='domcontentloaded')
            expect(page.get_by_role('heading',name='Library',exact=True)).to_be_visible()
            record('reader-return-library',passed=True)
            browser.close()
        report['status'] = 'PASS'
    except Exception as error:
        message = str(error)
        permission = any(term in message for term in ('Operation not permitted', 'No usable sandbox', 'Permission denied'))
        tls = 'ERR_CERT' in message
        report.update(status='BLOCKED' if permission or tls or stage != 'application' else 'FAIL',
                      failure_category='environment_permission' if permission else 'tls_trust' if tls else stage,
                      error_type=type(error).__name__)
        # Playwright errors may include submitted values: retain no raw exceptions.
        report['failure_signature'] = 'Operation not permitted / sandbox permission' if permission else 'Certificate verification failed' if tls else 'See failing stage; raw exception omitted to protect credentials'
        if screenshot_allowed and page and not page.is_closed():
            try:
                page.screenshot(path=str(args.output / 'failure.png'))
                report['failure_screenshot'] = 'failure.png'
            except Exception:
                pass
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
