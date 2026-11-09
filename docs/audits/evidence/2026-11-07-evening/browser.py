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
            screenshot_allowed = True
            stage='application'
            try:
                for width, height in VIEWPORTS:
                    stage = 'application'
                    page.set_viewport_size({'width': width, 'height': height})
                    response = page.goto(origin + '/', wait_until='domcontentloaded')
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
                    page.reload(wait_until='domcontentloaded')
                    assert page.locator('body').is_visible()
                    if not args.authenticated:
                        page.goto(origin + '/videos', wait_until='domcontentloaded')
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
            if args.authenticated:
                import hashlib, time
                report['discovery']={}
                discovery=report['discovery']
                page.set_viewport_size({'width':1440,'height':900})
                page.goto(origin+'/library',wait_until='domcontentloaded')
                page.get_by_role('textbox',name='Search saved notes').wait_for()
                expect(page.get_by_role('button',name='Refresh library',exact=True)).to_be_enabled(timeout=60000)
                page.get_by_role('textbox',name='Search saved notes').wait_for()
                expect(page.locator('.library-results-bar [role=status]')).to_contain_text('titles',timeout=60000)
                expected=int(__import__('re').match(r'(\d+)',page.locator('.library-results-bar [role=status]').inner_text()).group(1))
                expect(page.locator('a.library-card,article.series-card')).to_have_count(expected)
                search=page.get_by_role('textbox',name='Search saved notes')
                count_before=page.locator('a.library-card,article.series-card').count()
                search.fill('audit-20261107-no-match')
                expect(page.get_by_text('No matching notes',exact=True)).to_be_visible()
                search.fill('')
                expect(page.locator('a.library-card,article.series-card')).to_have_count(count_before)
                discovery['search']={'title_count':count_before,'cleared':True,'pagination_available':page.get_by_role('button',name='Show more notes').count()>0}
                ordinary=page.locator('a.library-card[data-kind="video"]').first
                ordinary.wait_for(timeout=60000)
                if ordinary.count():
                    report['discovery_stage']='open_reader'
                    ordinary.click()
                    note=page.locator('#video-content-scroll')
                    note.wait_for(timeout=60000)
                    expect(note).not_to_have_text('')
                    def prose():
                        note.locator('article[data-rendering=formatted]').wait_for(timeout=60000)
                        return ' '.join(note.locator('article[data-rendering=formatted]').evaluate('(el)=>{const c=el.cloneNode(true);c.querySelectorAll(".screenshot-block,.screenshot-caption,[role=status]").forEach(n=>n.remove());return c.textContent}').split())
                    current_hash=hashlib.sha256(prose().encode()).hexdigest()
                    discovery['reader']={'summary_nonempty':bool(note.inner_text().strip())}
                    report['discovery_stage']='transcript'
                    page.get_by_role('tab',name='Transcript',exact=True).click()
                    expect(page.get_by_role('tab',name='Transcript',exact=True)).to_have_attribute('aria-selected','true')
                    page.wait_for_timeout(1000)
                    discovery['reader']['transcript_empty_message']=page.get_by_text('No transcript available',exact=True).count()>0
                    discovery['reader']['transcript_panel_nonempty']=bool(page.locator('#video-transcript').inner_text().strip())
                    page.get_by_role('tab',name='Summary',exact=True).click()
                    report['discovery_stage']='reader_reload'
                    page.reload(wait_until='domcontentloaded')
                    page.get_by_role('tab',name='Summary',exact=True).wait_for(timeout=60000)
                    page.get_by_role('tab',name='Summary',exact=True).click()
                    note.wait_for(timeout=60000)
                    page.wait_for_timeout(1000)
                    report['discovery_stage']='summary_compare'
                    discovery['reader']['summary_same_after_reload']=hashlib.sha256(prose().encode()).hexdigest()==current_hash
                    # Expose only fixed toolbar labels, never titles or content.
                    more=page.get_by_role('button',name='More summary actions',exact=True)
                    discovery['reader']['more_actions_available']=more.count()>0
                    if more.count():
                        report['discovery_stage']='history'
                        more.click()
                        history=page.get_by_role('button',name='Version history',exact=True)
                        discovery['reader']['history_control_available']=history.count()>0
                        if history.count():
                            history.click()
                            versions=page.get_by_role('combobox',name='Note version')
                            versions.wait_for()
                            count=versions.locator('option').count()
                            discovery['reader']['version_choices']=count
                            if count>1:
                                with page.expect_response(lambda r:'/versions/' in urlsplit(r.url).path) as version_response:
                                    versions.select_option(index=1)
                                discovery['reader']['historical_version_http']=version_response.value.status
                                page.wait_for_timeout(1000)
                                discovery['reader']['historical_note_nonempty']=bool(note.inner_text().strip())
                                versions.select_option(index=0)
                                page.wait_for_timeout(500)
                                discovery['reader']['latest_restored']=hashlib.sha256(prose().encode()).hexdigest()==current_hash
                report['saved_markdown_unchanged_across_reads']=len(report['note_reads'])>=2 and len({r['markdown_sha256'] for r in report['note_reads']})==1
                report['discovery_stage']='task_history'
                page.goto(origin+'/',wait_until='domcontentloaded')
                page.wait_for_timeout(2000)
                task_button=page.get_by_role('button',name=__import__('re').compile('Task history|Review tasks')).first
                discovery['task_history_available']=task_button.count()>0
                if task_button.count():
                    task_button.click()
                    page.get_by_role('dialog',name='Task history').wait_for()
                    discovery['task_history_opened']=True
                page.goto(origin+'/podcasts',wait_until='domcontentloaded')
                ps=page.get_by_role('textbox',name='Search podcasts')
                ps.wait_for()
                ps.fill('audit-20261107-no-match')
                expect(page.get_by_text('No matching podcasts',exact=True)).to_be_visible(timeout=60000)
                ps.fill('')
                page.wait_for_timeout(1000)
                discovery['podcast_search']={'no_match_visible':True,'clear_succeeded':ps.input_value()=='','empty_account':page.get_by_text('No podcasts yet',exact=True).count()>0}
                page.reload(wait_until='domcontentloaded')
                page.get_by_role('textbox',name='Search podcasts').wait_for()
                discovery['podcast_search']['reload_succeeded']=True
                page.screenshot(path=str(args.output/'podcasts.png'))
            page.goto(origin+'/settings',wait_until='domcontentloaded')
            page.get_by_role('button',name='Platform Accounts',exact=True).click()
            page.get_by_role('button',name='YouTube',exact=True).click()
            section=page.get_by_role('region',name='YouTube verification')
            section.wait_for()
            field=section.get_by_role('textbox')
            field.fill('https://www.youtube.com/watch?v=PcO998TSzIs')
            import time
            started=time.monotonic()
            with page.expect_response(lambda r:urlsplit(r.url).path=='/api/cookies/youtube/verify',timeout=65000) as verification:
                section.get_by_role('button',name='Verify connection and download',exact=True).click()
            response=verification.value
            data=response.json()
            discovery['youtube_verification']={key:data.get(key) for key in ('reference','code','stage','cookie_present','metadata_ok','download_ok','sample_bytes','runtime')}
            discovery['youtube_verification']['http_status']=response.status
            discovery['youtube_verification']['observed_seconds']=round(time.monotonic()-started,2)
            expect(section.get_by_role('button',name='Verify connection and download',exact=True)).to_be_enabled(timeout=60000)
            discovery['youtube_verification']['retry_available']=True
            page.screenshot(path=str(args.output/'youtube-verification.png'))
            field.fill('')
            discovery['youtube_verification']['report_clears_on_input']=section.get_by_role('button',name='Copy diagnostic report',exact=True).count()==0
            page.reload(wait_until='domcontentloaded')
            discovery['settings_reload_logged_in']=urlsplit(page.url).path!='/login'
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
