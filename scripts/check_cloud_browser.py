"""Read-only cloud Chromium smoke checks; screenshots require separate human review."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

VIEWPORTS = [(1440, 900), (768, 1024), (390, 844)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://aipodcastsummary.online')
    parser.add_argument('--browser-path', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('appearance-checks/cloud-browser'))
    parser.add_argument('--authenticated', action='store_true',
                        help='Explicitly sign in using UI and BROWSER_TEST_EMAIL/PASSWORD environment variables')
    args = parser.parse_args()
    origin = args.origin.rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or parsed.netloc == '' or parsed.username or parsed.query or parsed.fragment or parsed.path:
        parser.error('--origin must be an HTTP(S) origin without credentials, path or query')
    email, password = os.environ.get('BROWSER_TEST_EMAIL'), os.environ.get('BROWSER_TEST_PASSWORD')
    if args.authenticated and not (email and password):
        parser.error('Authenticated mode requires BROWSER_TEST_EMAIL and BROWSER_TEST_PASSWORD; do not pass secrets as CLI arguments')
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
            try:
                for width, height in VIEWPORTS:
                    stage = 'application'
                    page.set_viewport_size({'width': width, 'height': height})
                    response = page.goto(origin + '/', wait_until='networkidle')
                    assert response and response.status == 200, 'Document did not load'
                    if args.authenticated:
                        assert urlsplit(page.url).path != '/login', 'Session lost'
                        control = page.locator('a[href="/library"]').first
                        control.click()
                        page.wait_for_url('**/library')
                        assert page.locator('main').is_visible(), 'Library main content missing'
                        interaction = 'Library navigation link clicked'
                    else:
                        assert urlsplit(page.url).path == '/login', 'Anonymous entry did not reach login'
                        checkbox = page.get_by_role('checkbox')
                        before = checkbox.is_checked()
                        checkbox.click()
                        assert checkbox.is_checked() != before, 'Checkbox did not change'
                        checkbox.click()
                        assert checkbox.is_checked() == before, 'Checkbox did not restore'
                        interaction = 'Remember me toggled and restored'
                    bounds = page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
                    assert bounds['scroll'] <= width, 'Horizontal overflow'
                    filename = f'{report["mode"]}-{width}x{height}.png'
                    page.screenshot(path=str(args.output / filename))
                    page.reload(wait_until='networkidle')
                    assert page.locator('body').is_visible()
                    if not args.authenticated:
                        page.goto(origin + '/videos', wait_until='networkidle')
                        assert urlsplit(page.url).path == '/login', 'Protected navigation did not reach login'
                    else:
                        assert urlsplit(page.url).path != '/login', 'Session lost after reload'
                    report['checks'].append({'viewport': [width, height], 'status': 'PASS',
                                             'interaction': interaction, 'reload': 'PASS',
                                             'screenshot': filename, 'horizontal_overflow': False})
            except Exception:
                if screenshot_allowed:
                    try:
                        page.screenshot(path=str(args.output / 'failure.png'))
                        report['failure_screenshot'] = 'failure.png'
                    except Exception:
                        pass
                raise
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
