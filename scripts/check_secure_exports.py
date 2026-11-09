"""Production-build local fixtures: token-free tabs, sandboxed HTML and PDF rendering.

The PDF is rendered by Chromium from the actual PDF button's print document.
This does not automate an OS Save dialog or contact any external provider.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from scripts.check_library_browser import serve, fixtures
from viewer import Summary, KeyPoint, export_html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    _, summary = fixtures()
    summary['overview'] += '\n\n| Signal | Action |\n|---|---|\n| Test | Review |\n'
    summary['key_points'][0]['original_quote'] = 'Synthetic original quote.'
    html = export_html(Summary(**{**summary, 'key_points': [KeyPoint(**v) for v in summary['key_points']]}))
    markdown = '# Synthetic episode\n\n## Measured topic\n\nBenchmark key point\n\n> Synthetic original quote.\n\n| Signal | Action |\n|---|---|\n| Test | Review |\n'
    server = serve(Path(__file__).resolve().parents[1] / 'web/dist')
    origin = f'http://127.0.0.1:{server.server_port}'
    result = {'environment': 'local synthetic APIs, production frontend build', 'screenshots': [], 'checks': {}}
    requests = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', chromium_sandbox=True, headless=True)
        context = browser.new_context(ignore_https_errors=False)
        failure = False
        def api(route):
            nonlocal failure
            path = urlsplit(route.request.url).path
            body = {}
            if path == '/api/auth/config': body = {'supabase_enabled': True}
            elif path == '/api/auth/me': body = {'id': 'synthetic-owner', 'email': '', 'authenticated': True}
            elif path == '/api/summaries/bench': body = summary
            elif path == '/api/summaries/bench/html':
                requests.append({'query_empty': not urlsplit(route.request.url).query, 'has_header': route.request.headers.get('authorization') == 'Bearer synthetic-session'})
                return route.fulfill(status=524 if failure else 200, body='Gateway timeout' if failure else html, content_type='text/html')
            elif path == '/api/summaries/bench/markdown': body = {'markdown': markdown}
            route.fulfill(json=body)
        context.route('**/api/**', api)
        context.add_init_script("""
          window.WebSocket=class {static OPEN=1;readyState=1;send(){}close(){}};
          const create=URL.createObjectURL.bind(URL);
          URL.createObjectURL=blob=>{if(blob.type==='text/html')blob.text().then(text=>window.__printDocument=text);return create(blob)};
        """)
        page = context.new_page(); page.goto(origin + '/login')
        # A synthetic local fixture session only; no production token creation.
        page.evaluate("""()=>{sessionStorage.setItem('xyz_access_token','synthetic-session');sessionStorage.setItem('xyz_user',JSON.stringify({id:'synthetic-owner',email:'',authenticated:true}));localStorage.removeItem('xyz_remember_me')}""")
        page.goto(origin + '/viewer/bench'); expect(page.locator('#podcast-summary')).to_be_visible()
        page.get_by_role('button', name='Export', exact=True).click()
        with context.expect_page() as opened: page.get_by_role('button', name='Open as HTML', exact=True).click()
        exported = opened.value
        frame = exported.frame_locator('iframe[title="Summary HTML export"]')
        expect(frame.get_by_text('Benchmark key point', exact=True)).to_be_visible()
        assert exported.url == origin + '/exports/summaries/bench'
        assert exported.evaluate('window.opener === null')
        assert exported.locator('iframe').get_attribute('sandbox') == ''
        frame.locator('details summary').click(); expect(frame.locator('blockquote')).to_be_visible()
        exported.reload(); expect(frame.get_by_text('Benchmark key point', exact=True)).to_be_visible()
        result['checks']['session_only_tab_refresh_opener_null'] = True
        result['checks']['native_quote_expansion'] = True
        for width, height in [(1440,900),(768,1024),(390,844)]:
            exported.set_viewport_size({'width':width,'height':height})
            assert not frame.locator('html').evaluate('e=>e.scrollWidth>innerWidth')
            filename = f'html-{width}x{height}.png'; exported.screenshot(path=str(args.output/filename))
            result['screenshots'].append(filename)
        failure = True; exported.reload(); expect(exported.get_by_role('alert')).to_contain_text('HTTP 524')
        failure = False; exported.get_by_role('button',name='Retry export').click()
        expect(frame.get_by_text('Benchmark key point',exact=True)).to_be_visible()
        result['checks']['html_error_retry'] = True
        page.get_by_role('button',name='Export',exact=True).click(); page.get_by_role('button',name='PDF',exact=True).click()
        page.wait_for_function('Boolean(window.__printDocument)')
        print_html = page.evaluate('window.__printDocument')
        assert 'Benchmark key point' in print_html and '<table>' in print_html
        pdf_page = context.new_page(); pdf_page.set_content(print_html,wait_until='load')
        pdf_page.pdf(path=str(args.output/'synthetic-export.pdf'),format='A4',print_background=True)
        result['checks']['actual_pdf_button_document_rendered_by_chromium'] = True
        result['checks']['os_save_dialog'] = 'not exercised: headless Chromium'
        assert requests and all(r['query_empty'] and r['has_header'] for r in requests)
        result['checks']['all_html_fetches_header_only'] = True
        result['status']='PASS'
        (args.output/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result)); browser.close()
    server.shutdown()

if __name__ == '__main__': main()
