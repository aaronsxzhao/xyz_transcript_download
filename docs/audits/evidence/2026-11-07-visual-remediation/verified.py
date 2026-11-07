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

VIEWPORTS = []


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
            stage = 'application'
            findings = {}
            task_observations=[]
            def observe(response):
                path=urlsplit(response.url).path
                if path.startswith('/api/video-notes/tasks/') and len(path.strip('/').split('/'))==4 and response.status==200:
                    body=response.json()
                    task_observations.append({'channel_missing':not bool(body.get('channel')),'has_markdown':bool(body.get('markdown')),'status':body.get('status')})
            page.on('response',observe)
            def save():
                (args.output/'findings.json').write_text(json.dumps(findings,indent=2))
            def shot(name):
                page.screenshot(path=str(args.output/(name+'.png')))
            page.set_viewport_size({'width':1440,'height':900})
            with page.expect_response(lambda r: urlsplit(r.url).path == '/api/video-notes/channels') as pending:
                page.goto(origin+'/videos',wait_until='networkidle')
            resp=pending.value
            data=resp.json()
            findings['channels']={'http':resp.status,'count':len(data.get('channels',[])),'total':sum(x.get('total',0) for x in data.get('channels',[]))}
            page.wait_for_timeout(1500)
            shot('videos-ready')
            findings['videos_empty_visible']=page.get_by_text('No video notes yet',exact=True).is_visible()
            save()
            page.goto(origin+'/library',wait_until='networkidle')
            expect(page.get_by_role('button',name='Refresh library',exact=True)).to_be_enabled(timeout=60000)
            expect(page.locator('.series-card')).to_be_visible()
            findings['library_cards']=page.locator('a.library-card, .series-card').count()
            page.locator('a.library-card').first.click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            findings['initial_formatted']=True
            shot('reader-initial')
            page.get_by_role('tab',name='Transcript',exact=True).click()
            expect(page.locator('#video-transcript')).to_be_visible()
            page.get_by_role('tab',name='Summary',exact=True).click()
            expect(page.get_by_role('tab',name='Summary',exact=True)).to_have_attribute('aria-selected','true')
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=20000)
            before_title=page.locator('h1').first.inner_text()
            with page.expect_response(lambda r:urlsplit(r.url).path.startswith('/api/video-notes/tasks/') and len(urlsplit(r.url).path.strip('/').split('/'))==4 and r.status==200):
                page.reload(wait_until='domcontentloaded')
            expect(page.get_by_role('tab',name='Summary',exact=True)).to_have_attribute('aria-selected','true')
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            assert page.locator('h1').first.inner_text()==before_title
            assert len(page.locator('article[data-rendering="formatted"]').inner_text())>1000
            findings['protected_note_reload_200']=True
            findings['same_title_after_reload']=True
            page.wait_for_timeout(3000)
            findings['after_reload']={'summary_selected':page.get_by_role('tab',name='Summary',exact=True).get_attribute('aria-selected'),'article_count':page.locator('article').count(),'formatted_count':page.locator('article[data-rendering="formatted"]').count(),'plain_count':page.locator('article[data-rendering="plain"]').count(),'formatted_visible':page.locator('article[data-rendering="formatted"]').first.is_visible(),'main_scroll':page.locator('main').evaluate('(e)=>e.scrollTop'),'summary_panel_hidden':page.locator('#video-markdown').get_attribute('hidden')}
            shot('reader-reloaded'); save()
            try:
                expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=20000)
                findings['refresh_assertion']='PASS'
            except Exception:
                findings['refresh_assertion']='FAIL'
            findings['task_metadata']=task_observations
            page.goto(origin+'/library',wait_until='domcontentloaded')
            expect(page.get_by_role('button',name='Refresh library',exact=True)).to_be_enabled(timeout=60000)
            page.get_by_role('button',name='View episodes',exact=True).first.click()
            page.locator('.series-episodes a').first.click()
            expect(page.locator('article[data-rendering="formatted"]')).to_be_visible(timeout=60000)
            page.wait_for_timeout(1000)
            findings['task_metadata']=task_observations
            save()
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
