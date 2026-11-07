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
            try:
                for width, height in VIEWPORTS:
                    stage = 'application'
                    page.set_viewport_size({'width': width, 'height': height})
                    response = page.goto(origin + '/', wait_until='networkidle')
                    assert response and response.status == 200, 'Document did not load'
                    if args.authenticated:
                        assert urlsplit(page.url).path != '/login', 'Session lost'
                        control = page.locator('a[href="/library"]').first
                        if not control.is_visible():
                            page.get_by_role('button', name='Open navigation', exact=True).click()
                            control = page.locator('a[href="/library"]:visible').first
                        control.click()
                        page.wait_for_url('**/library')
                        assert page.locator('main').is_visible(), 'Library main content missing'
                        expect(page.get_by_role('button', name='Refresh library', exact=True)).to_be_enabled(timeout=60000)
                        expect(page.locator('.library-results-bar [role="status"]')).not_to_contain_text('Loading your notes')
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
            report['discovery'] = []
            def capture(name):
                page.wait_for_timeout(800)
                page.screenshot(path=str(args.output / (name + '.png')))
                report['discovery'].append({'name':name,'width':page.viewport_size['width'],'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth'),'design':page.locator('html').get_attribute('data-design'),'theme':page.locator('html').get_attribute('data-theme')})
                (args.output / 'discovery.json').write_text(json.dumps(report['discovery'],indent=2))
            def library_ready():
                expect(page.get_by_role('button', name='Refresh library',exact=True)).to_be_enabled(timeout=60000)
                expect(page.locator('.library-results-bar [role="status"]')).to_contain_text('titles')
                expect(page.locator('.series-card')).to_be_visible(timeout=20000)
            def set_theme(design,theme):
                page.get_by_label('Interface style',exact=True).select_option(design)
                expect(page.get_by_label('Interface style',exact=True)).to_be_enabled()
                toggle=page.get_by_role('button',name='Switch to '+theme+' mode',exact=True)
                if toggle.count(): toggle.click()
                expect(page.get_by_label('Interface style',exact=True)).to_be_enabled()
            def response_evidence(r):
                path=urlsplit(r.url).path
                category='series_parts' if '/collections/' in path and path.endswith('/parts') else 'historical_image' if 'screenshot' in path else None
                if category: report.setdefault('response_statuses',[]).append({'category':category,'status':r.status})
            page.on('response',response_evidence)
            page.set_viewport_size({'width':1440,'height':900})
            page.goto(origin+'/library',wait_until='networkidle'); library_ready()
            for design in ['classic','editorial']:
                for theme in ['light','dark']:
                    set_theme(design,theme)
                    page.reload(wait_until='networkidle'); library_ready()
                    for width,height in [(1440,900),(768,1024),(390,844)]:
                        page.set_viewport_size({'width':width,'height':height})
                        capture('library-'+design+'-'+theme+'-'+str(width))
            page.set_viewport_size({'width':1440,'height':900})
            set_theme('classic','dark')
            page.get_by_role('button',name='View episodes',exact=True).first.click()
            expect(page.get_by_role('button',name='Hide episodes',exact=True).first).to_have_attribute('aria-expanded','true')
            page.wait_for_timeout(2000); capture('series-error')
            episode=page.locator('.series-episodes a').first
            episode.click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            capture('episode-reader')
            transcript=page.get_by_role('button',name='Transcript',exact=True)
            if transcript.count():
                transcript.click(); page.wait_for_timeout(1500); capture('episode-transcript')
            page.go_back(wait_until='networkidle'); library_ready()
            page.reload(wait_until='networkidle'); library_ready()
            report['series_reader_back_reload']='PASS'
            page.goto(origin+'/',wait_until='networkidle')
            page.get_by_text('Task history',exact=False).first.click()
            expect(page.get_by_role('dialog')).to_be_visible()
            capture('task-history')
            page.get_by_role('dialog').get_by_role('link',name='Read summary',exact=True).first.click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            capture('task-reader')
            page.reload(wait_until='networkidle')
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            report['task_reader_refresh']='PASS'
            page.goto(origin+'/settings',wait_until='networkidle')
            expect(page.get_by_role('heading',name='Settings',exact=True)).to_be_visible()
            page.wait_for_timeout(2000)
            # Hide values of all settings inputs in screenshots, including saved account-specific values.
            def settings_shot(name):
                page.screenshot(path=str(args.output/(name+'.png')),mask=[page.locator('input'),page.locator('textarea')])
                report['discovery'].append({'name':name,'inputs_masked':True})
            settings_shot('settings-general')
            labels=page.locator('.settings-tabs button').all_text_contents()
            report['settings_tabs']=labels
            for i in range(1,len(labels)):
                page.locator('.settings-tabs button').nth(i).click()
                page.wait_for_timeout(1000)
                settings_shot('settings-tab-'+str(i))
            page.reload(wait_until='networkidle')
            report['settings_tabs_reload']='PASS; no saves or connection tests'
            page.goto(origin+'/podcasts',wait_until='networkidle'); capture('podcasts-empty')
            page.goto(origin+'/videos',wait_until='networkidle'); capture('videos')
            (args.output/'discovery.json').write_text(json.dumps(report['discovery'],indent=2))
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
