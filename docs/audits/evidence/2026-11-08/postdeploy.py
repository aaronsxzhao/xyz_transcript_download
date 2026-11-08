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

VIEWPORTS = [(1440,900),(768,1024),(390,844)]


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
                if request.method == 'POST' and request.url == origin + '/api/cookies/youtube/verify':
                    return route.continue_()
                if login_allowed and request.method == 'POST' and request.url == origin + '/api/auth/signin':
                    return route.continue_()
                report['blocked_write_requests'] += 1
                route.abort()

            context.route('**/*', guard)
            page = context.new_page()
            page.set_default_timeout(20000)
            report['network_errors']=[]
            report['note_reads']=[]
            report['page_error_count']=0
            report['console_error_count']=0
            def console_error(message):
                if message.type=='error': report['console_error_count']+=1
            page.on('console',console_error)
            def network(response):
                path=urlsplit(response.url).path
                if response.status==200 and path.startswith('/api/video-notes/tasks/') and len(path.strip('/').split('/'))==4:
                    try:
                        data=response.json()
                        report['note_reads'].append({'markdown_sha256':__import__('hashlib').sha256((data.get('markdown') or '').encode()).hexdigest(),'status':data.get('status'),'versions':len(data.get('versions',[]))})
                    except Exception: pass
                if response.status>=400:
                    report['network_errors'].append({'status':response.status,'resource_kind': 'screenshot' if 'screenshot' in path else 'image' if any(path.endswith(x) for x in ('.png','.jpg','.webp')) else 'other', 'category':'collection_parts' if '/collections/' in path and path.endswith('/parts') else 'transcript' if 'transcript' in path else 'api' if path.startswith('/api/') else 'asset'})
            page.on('response',network)
            def page_error(error): report['page_error_count']+=1
            page.on('pageerror',page_error)
            if args.authenticated:
                stage = 'authentication'
                page.goto(origin + '/login', wait_until='domcontentloaded')
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
                    page.goto(origin + '/', wait_until='domcontentloaded')
                assert pending.value.status == 200, 'Protected API rejected session'
                report['authenticated_session_verified'] = True
            screenshot_allowed=True
            stage='application'
            page.set_viewport_size({'width':1440,'height':900})
            page.goto(origin+'/settings',wait_until='domcontentloaded')
            page.get_by_role('button',name='Platform Accounts',exact=True).click()
            page.get_by_role('button',name='YouTube',exact=True).click()
            section=page.get_by_role('region',name='YouTube verification')
            section.wait_for()
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/cookies/youtube/verify',timeout=65000) as verification:
                section.get_by_role('button',name='Verify connection and download',exact=True).click()
            response=verification.value
            data=response.json()
            report['verification']={key:data.get(key) for key in ('reference','revision','code','stage','cookie_present','metadata_ok','download_ok','sample_bytes','elapsed_seconds')}
            expect(section.get_by_role('button',name='Verify connection and download',exact=True)).to_be_enabled(timeout=60000)
            report['verification']['retry_available']=True
            report['verification']['missing_label']=section.get_by_text('Saved cookies: missing',exact=True).count()>0
            page.screenshot(path=str(args.output/'youtube-postdeploy.png'))
            assert data.get('code')=='missing_cookie', 'Expected absent-cookie diagnostic for this account'
            assert data.get('stage')=='cookie'
            assert report['verification']['missing_label']
            browser.close()
        report['status'] = 'PASS'
    except Exception as error:
        message = str(error)
        report['timeout_at']=report.get('discovery_stage','setup')
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
