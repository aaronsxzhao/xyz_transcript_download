"""Read-only live browser checks. Emit numbers, never page data or credentials."""
import asyncio
import json
import re
import time
from urllib.parse import urlparse

ORIGIN = 'https://aipodcastsummary.online'


async def profile_browser(owner: str, token: str) -> list[dict]:
    from playwright.async_api import async_playwright
    reports = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 390, 'height': 844})
        # This five-minute diagnostic token exists only in the disposable browser
        # context. Do not save its storage state, screenshots, traces, or HARs.
        await context.add_init_script('''
          localStorage.setItem('xyz_remember_me','true');
          localStorage.setItem('xyz_access_token',TOKEN);
          localStorage.setItem('xyz_user',JSON.stringify({id:OWNER,email:'',authenticated:true}));
        '''.replace('TOKEN', json.dumps(token)).replace('OWNER', json.dumps(owner)))

        async def read_only(route):
            request = route.request
            if not request.url.startswith(ORIGIN + '/'):
                return await route.abort()
            if urlparse(request.url).path == '/api/performance':
                # Keep synthetic visits out of the real user's timing samples.
                return await route.fulfill(status=204)
            if request.method not in {'GET', 'HEAD'}:
                return await route.abort()
            await route.continue_()

        await context.route('**/*', read_only)
        routes = [
            ('episodes', '/podcasts/62382c1103bea1ebfffa1c00/episodes', '/api/podcasts/62382c1103bea1ebfffa1c00/episodes'),
            ('channel', '/videos?platform=youtube&channel=Brooks+Trading+Course', '/api/video-notes/tasks/by-channel'),
            ('summary', '/viewer/694b7d6d0b60b7bf752e007b', '/api/summaries/694b7d6d0b60b7bf752e007b'),
            ('video_note', '/videos/bc2c988b-2b4', '/api/video-notes/tasks/bc2c988b-2b4'),
            ('library', '/library', '/api/summaries'),
            ('settings', '/settings', '/api/settings'),
        ]
        for label, path, critical in routes:
            page = await context.new_page()
            errors, failed = [], []
            page.on('pageerror', lambda error: errors.append(1))
            page.on('requestfailed', lambda request: failed.append(1)
                    if request.url.startswith(ORIGIN + '/assets/') else None)
            started = time.perf_counter()
            report = {'library_profile': 'check_' + label, 'status': 0}
            try:
                async with page.expect_response(lambda response: urlparse(response.url).path == critical, timeout=25000) as pending:
                    await page.goto(ORIGIN + path, wait_until='domcontentloaded', timeout=25000)
                response = await pending.value
                report['status'] = response.status
                data = await response.json()
                if response.status != 200:
                    raise RuntimeError('Page API check failed')
                if label == 'summary':
                    await page.get_by_role('heading', name='Overview', exact=True).wait_for(timeout=10000)
                elif label in {'episodes', 'channel'}:
                    rows = data if isinstance(data, list) else data['tasks']
                    if rows:
                        await page.get_by_text(rows[0]['title'], exact=True).first.wait_for(timeout=10000)
                elif label == 'library':
                    await page.get_by_role('heading', name='Library', exact=True).wait_for(timeout=10000)
                    await page.locator('main a[href^="/viewer/"], main a[href^="/videos/"]').first.wait_for(timeout=10000)
                elif label == 'video_note':
                    await page.locator('article').wait_for(timeout=10000)
                    report['note_ready_ms'] = round((time.perf_counter() - started) * 1000)
                    images = await page.locator('article img').element_handles()
                    loaded = 0
                    for img in images:
                        try:
                            await img.scroll_into_view_if_needed(timeout=3000)
                            await page.wait_for_function('(image) => image.complete', arg=img, timeout=10000)
                            loaded += int(await img.evaluate('(image) => image.naturalWidth > 0'))
                        except Exception:
                            pass
                    expected = len(set(re.findall(r'/data/screenshots/[A-Za-z0-9_.-]+', data.get('markdown', ''))))
                    report.update(loaded_images=loaded, missing_images=max(expected, len(images)) - loaded)
                    mark_started = time.perf_counter()
                    await page.get_by_role('button', name='Mind Map', exact=True).click()
                    await page.locator('svg.markmap foreignObject').first.wait_for(timeout=15000)
                    report['mindmap_ms'] = round((time.perf_counter() - mark_started) * 1000)
                    await page.get_by_role('button', name=re.compile('zoom in', re.I)).click()
                    await page.get_by_role('button', name=re.compile('fit to view', re.I)).click()
                    note_started = time.perf_counter()
                    await page.get_by_role('button', name='Note', exact=True).click()
                    await page.locator('article').wait_for(state='visible', timeout=5000)
                    report['return_to_note_ms'] = round((time.perf_counter() - note_started) * 1000)
                else:
                    await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]')?.disabled")
                report['milliseconds'] = round((time.perf_counter() - started) * 1000)
            except Exception:
                report['status'] = 500
            report.update(js_errors=len(errors), failed_requests=len(failed))
            if errors or failed:
                report['status'] = 500
            reports.append(report)
            await page.close()
        await context.close()
        await browser.close()
    return reports
