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
    parser.add_argument('--baseline-results',type=Path,required=True,help='Prior sanitized owned-P2 response hash report')
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
            pending_assets=set()
            failed_assets=[]
            def asset_request(request):
                if urlsplit(request.url).netloc==parsed.netloc and request.resource_type in ('script','stylesheet'):
                    pending_assets.add(request.url)
            def asset_done(request): pending_assets.discard(request.url)
            def asset_failed(request):
                if request.url in pending_assets: failed_assets.append(request.resource_type)
                pending_assets.discard(request.url)
            page.on('request',asset_request)
            page.on('requestfinished',asset_done)
            page.on('requestfailed',asset_failed)
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
                    if response.request.resource_type in ('script','stylesheet') and urlsplit(response.url).netloc==parsed.netloc:
                        failed_assets.append(response.request.resource_type)
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
            page.goto(origin+'/library',wait_until='domcontentloaded')
            search=page.get_by_role('textbox',name='Search saved notes')
            search.wait_for(timeout=60000)
            expect(page.locator('a.library-card,article.series-card')).to_have_count(2,timeout=60000)
            search.fill('audit-20261108-no-match')
            expect(page.get_by_text('No matching notes',exact=True)).to_be_visible()
            search.fill('')
            expect(page.locator('a.library-card,article.series-card')).to_have_count(2)
            report['library']={'titles':2,'search_and_clear':True,'pagination_available':page.get_by_role('button',name='Show more notes').count()>0}
            page.locator('a.library-card[data-kind="video"]').first.click(timeout=60000)
            article=page.locator('#video-content-scroll article[data-rendering=formatted]')
            def snap():
                import time
                article.wait_for(timeout=60000)
                deadline=time.monotonic()+30
                previous=None
                stable_since=None
                while time.monotonic()<deadline:
                    page.wait_for_timeout(100)
                    assert not failed_assets, 'Reader script or stylesheet failed'
                    if pending_assets:
                        stable_since=None
                        continue
                    current=article.evaluate("el=>{const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let text='',n;while(n=w.nextNode()){if(!n.parentElement.closest('.screenshot-block,.screenshot-caption,[role=status]'))text+=n.textContent;}return {text:text.replace(/\\s+/g,' ').trim(),math:el.querySelectorAll('.katex').length}}")
                    if current != previous:
                        previous=current;stable_since=time.monotonic()
                    elif stable_since is None: stable_since=time.monotonic()
                    elif time.monotonic()-stable_since>=1:
                        return current
                report['reader_timeout']={'pending_assets':[urlsplit(url).path for url in pending_assets],'failed_assets':failed_assets,'last_math_nodes':previous['math'] if previous else None,'last_text_length':len(previous['text']) if previous else None}
                page.screenshot(path=str(args.output/'reader-not-settled.png'))
                raise AssertionError('Reader assets/text did not settle')
            import hashlib,time
            before=snap()
            page.screenshot(path=str(args.output/'reader-settled.png'))
            with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/transcript')) as transcript_response:
                page.get_by_role('tab',name='Transcript',exact=True).click()
            assert transcript_response.value.status==200
            transcript_payload=transcript_response.value.json().get('transcript') or {}
            assert transcript_payload.get('text') or transcript_payload.get('segments')
            expect(page.get_by_role('tab',name='Transcript',exact=True)).to_have_attribute('aria-selected','true')
            expect(page.locator('#video-transcript')).not_to_be_empty()
            report['transcript']={'panel_nonempty':bool(page.locator('#video-transcript').inner_text().strip()),'empty_message':page.get_by_text('No transcript available',exact=True).count()>0}
            page.get_by_role('tab',name='Summary',exact=True).click()
            page.get_by_role('button',name='More summary actions',exact=True).click()
            page.get_by_role('button',name='Version history',exact=True).click()
            versions=page.get_by_role('combobox',name='Note version')
            with page.expect_response(lambda r:'/versions/' in urlsplit(r.url).path) as historical:
                versions.select_option(index=1)
            assert historical.value.status==200
            historical_body=historical.value.json().get('content') or ''
            assert historical_body.strip()
            historical_snap=snap()
            assert historical_snap['text']
            report['historical_version']={'http_status':200,'saved_body_nonempty':True,'rendered_body_nonempty':True}
            versions.select_option(index=0)
            page.wait_for_timeout(500)
            restored=snap()
            assert restored['text']==before['text'], 'Latest version did not restore settled body'
            report['version_restore']={'equal':restored['text']==before['text'],'math_counts':[before['math'],restored['math']],'lengths':[len(before['text']),len(restored['text'])]}
            page.wait_for_timeout(2500)
            settled=snap()
            page.reload(wait_until='domcontentloaded')
            article.wait_for(timeout=60000)
            page.wait_for_timeout(2500)
            after=snap()
            assert before['text']==settled['text']==after['text'], 'Settled reader text differs after reload'
            report['reader_timing']={'initial_math':before['math'],'settled_math':settled['math'],'reload_math':after['math'],'initial_equals_settled':before['text']==settled['text'],'settled_equals_reload':settled['text']==after['text'],'text_lengths':[len(x['text']) for x in (before,settled,after)]}
            page.goto(origin+'/library',wait_until='domcontentloaded')
            series=page.locator('article.series-card').first
            started=time.monotonic()
            with page.expect_response(lambda r:'/api/video-notes/collections/' in r.url and r.url.endswith('/parts')) as pending:
                series.get_by_role('button',name='View episodes').click(timeout=60000)
            report['collection_status']=pending.value.status
            report['collection_seconds']=round(time.monotonic()-started,3)
            parts=pending.value.json()['parts'] if pending.value.status==200 else []
            report['collection_part_count']=len(parts)
            if parts:
                assert len(parts)==2 and [part['page'] for part in parts]==[1,2]
                assert parts[1]['task_id'] and parts[1]['status']=='success'
                expect(series.locator('.series-episodes li')).to_have_count(2)
                expect(series.get_by_role('alert')).to_have_count(0)
                saved=parts[1]['task_id']
            else:
                fallback=series.locator('a[href^="/videos/"]').first
                fallback.wait_for()
                saved=fallback.get_attribute('href').rsplit('/',1)[-1]
                report['directory_failure_preserves_saved_link']=True
            with page.expect_response(lambda r:urlsplit(r.url).path==f'/api/video-notes/tasks/{saved}') as saved_response:
                series.locator(f'a[href="/videos/{saved}"]').click()
            assert saved_response.value.status==200
            before_p2=json.loads(args.baseline_results.read_text())['note_reads'][0]['markdown_sha256']
            after_p2=__import__('hashlib').sha256((saved_response.value.json().get('markdown') or '').encode()).hexdigest()
            assert before_p2==after_p2, 'Saved P2 body changed'
            report['saved_p2_markdown_unchanged']=True
            saved_article=page.locator('#video-content-scroll article[data-rendering=formatted]')
            expect(saved_article).to_be_visible(timeout=60000)
            assert saved_article.inner_text().strip()
            report['saved_p2_opened']=True
            page.goto(origin+'/library',wait_until='domcontentloaded')
            series=page.locator('article.series-card').first
            with page.expect_response(lambda r: '/api/video-notes/collections/' in r.url and r.url.endswith('/parts')) as refreshed:
                series.get_by_role('button',name='View episodes').click()
            again=refreshed.value.json()['parts'] if refreshed.value.status==200 else []
            if parts and again:
                assert [(x['page'],x['task_id'],x['status']) for x in again]==[(x['page'],x['task_id'],x['status']) for x in parts]
            report['collection_after_return']={'http':refreshed.value.status,'parts':len(again),'saved_p2_identity_unchanged':bool(parts and again)}
            page.reload(wait_until='domcontentloaded')
            series=page.locator('article.series-card').first
            with page.expect_response(lambda r:'/api/video-notes/collections/' in r.url and r.url.endswith('/parts')) as reloaded:
                series.get_by_role('button',name='View episodes').click(timeout=60000)
            reload_parts=reloaded.value.json()['parts'] if reloaded.value.status==200 else []
            if parts and reload_parts:
                assert [(x['page'],x['task_id'],x['status'],x.get('progress')) for x in reload_parts]==[(x['page'],x['task_id'],x['status'],x.get('progress')) for x in parts]
            report['collection_after_reload']={'http':reloaded.value.status,'parts':len(reload_parts),'statuses_unchanged':bool(parts and reload_parts)}
            for width,height in VIEWPORTS:
                page.set_viewport_size({'width':width,'height':height})
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'), 'Horizontal overflow'
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=str(args.output/f'library-{width}.png'))
                series.locator('.series-episodes').screenshot(path=str(args.output/f'episodes-{width}.png'))
            page.goto(origin+'/',wait_until='domcontentloaded')
            task_button=page.get_by_role('button',name=__import__('re').compile('Task history|Review tasks')).first
            task_button.wait_for(timeout=60000)
            task_button.click()
            page.get_by_role('dialog',name='Task history').wait_for()
            report['task_history_opened']=True
            page.goto(origin+'/settings',wait_until='domcontentloaded')
            page.get_by_role('button',name='Tools & Data',exact=True).click()
            with page.expect_response(lambda r:'/api/maintenance/media-integrity' in r.url,timeout=60000) as integrity:
                page.get_by_role('button',name='Check missing screenshots',exact=True).click()
            ir=integrity.value
            assert ir.status==200
            integrity_data=ir.json()
            report['media_integrity']={'http_status':ir.status,'referenced':integrity_data.get('referenced'),'missing':integrity_data.get('missing'),'affected_notes':len(integrity_data.get('notes',[]))}
            browser.close()
        report['status'] = 'PASS' if report.get('collection_status')==200 and report.get('collection_after_return',{}).get('http')==200 and report.get('collection_after_reload',{}).get('http')==200 else 'FAIL'
    except Exception as error:
        message = str(error)
        tb=error.__traceback__
        while tb:
            if tb.tb_frame.f_code.co_filename==__file__: report['harness_failure_line']=tb.tb_lineno
            tb=tb.tb_next
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
