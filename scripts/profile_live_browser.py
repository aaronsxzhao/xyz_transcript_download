"""Read-only live browser checks. Emit numbers, never page data or credentials."""
import asyncio
import json
import re
import time
from urllib.parse import urlparse

ORIGIN = 'https://aipodcastsummary.online'


async def profile_browser(owner: str, token: str, local_video: str | None = None) -> list[dict]:
    from playwright.async_api import async_playwright
    reports = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
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
            ('episode_navigation', '/podcasts?platform=xiaoyuzhou', '/api/podcasts/6540c81e9cb67569a2f99856/episodes'),
            ('episodes', '/podcasts/62382c1103bea1ebfffa1c00/episodes', '/api/podcasts/62382c1103bea1ebfffa1c00/episodes'),
            ('channel', '/videos?platform=youtube&channel=Brooks+Trading+Course', '/api/video-notes/tasks/by-channel'),
            ('summary', '/viewer/69b1512984bce022f9ea354c', '/api/summaries/69b1512984bce022f9ea354c'),
            ('video_note', '/videos/bc2c988b-2b4', '/api/video-notes/tasks/bc2c988b-2b4'),
            ('library', '/library', '/api/library'),
            ('settings', '/settings', '/api/settings'),
        ]
        routes.append(('latest_summary', '/viewer/699acfb5de29766da924dee1', '/api/summaries/699acfb5de29766da924dee1'))
        if local_video:
            routes.append(('local_video_note', '/videos/' + local_video, '/api/video-notes/tasks/' + local_video))
        for label, path, critical in routes:
            page = await context.new_page()
            errors, failed, image_server_errors = [], [], []
            page.on('response', lambda response: image_server_errors.append(1)
                    if response.status >= 500 and urlparse(response.url).path.startswith('/data/') else None)
            page.on('pageerror', lambda error: errors.append(1))
            page.on('requestfailed', lambda request: failed.append(1)
                    if request.url.startswith(ORIGIN + '/assets/') else None)
            started = time.perf_counter()
            report = {'library_profile': 'check_' + label, 'status': 0}
            try:
                async with page.expect_response(lambda response: urlparse(response.url).path == critical, timeout=25000) as pending:
                    await page.goto(ORIGIN + path, wait_until='domcontentloaded', timeout=25000)
                    if label == 'episode_navigation':
                        await page.locator('a[href="/podcasts/6540c81e9cb67569a2f99856/episodes"]').click(timeout=15000)
                response = await pending.value
                report['status'] = response.status
                data = await response.json()
                if response.status != 200:
                    raise RuntimeError('Page API check failed')
                if label in {'summary', 'latest_summary'}:
                    await page.get_by_role('heading', name='Overview', exact=True).wait_for(timeout=10000)
                    report['topic_columns'] = await page.locator('[data-topic-column]').count()
                elif label in {'episodes', 'episode_navigation', 'channel'}:
                    rows = data if isinstance(data, list) else data['tasks']
                    if rows:
                        await page.get_by_text(rows[0]['title'], exact=True).first.wait_for(timeout=10000)
                elif label == 'library':
                    await page.get_by_role('heading', name='Library', exact=True).wait_for(timeout=10000)
                    await page.locator('main a[href^="/viewer/"], main a[href^="/videos/"]').first.wait_for(timeout=10000)
                elif label in {'video_note', 'local_video_note'}:
                    await page.locator('article').wait_for(timeout=10000)
                    report['note_ready_ms'] = round((time.perf_counter() - started) * 1000)
                    try:
                        await page.locator('article[data-rendering="formatted"]').wait_for(timeout=5000)
                    except Exception:
                        await page.wait_for_timeout(300)
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
                    bounds = await page.locator('article img').evaluate_all('(nodes)=>nodes.map(n=>{const r=n.getBoundingClientRect();return [r.width,r.height]})')
                    report['largest_preview_width'] = round(max((r[0] for r in bounds), default=0))
                    report['largest_preview_height'] = round(max((r[1] for r in bounds), default=0))
                    if report['largest_preview_width'] > 761 or report['largest_preview_height'] > 421:
                        raise RuntimeError('Screenshot preview exceeds reader bounds')
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
                    await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=10000)
                    await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]')?.disabled")
                document = await page.evaluate("(() => {const n=performance.getEntriesByType('navigation')[0];return [n?.encodedBodySize||0,n?.decodedBodySize||0]})()")
                report['document_wire_bytes'], report['document_decoded_bytes'] = document
                report['first_paint_ms'] = await page.evaluate("Math.round(performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0)")
                sizes = await page.evaluate("(() => {const r=performance.getEntriesByType('resource').filter(e=>new URL(e.name).pathname.startsWith('/assets/'));return [r.reduce((s,e)=>s+e.encodedBodySize,0),r.reduce((s,e)=>s+e.decodedBodySize,0)]})()")
                report['asset_wire_bytes'], report['asset_decoded_bytes'] = sizes
                report['milliseconds'] = round((time.perf_counter() - started) * 1000)
            except Exception:
                report['status'] = 500
            report.update(js_errors=len(errors), failed_requests=len(failed), image_server_errors=len(image_server_errors))
            if errors or failed or image_server_errors:
                report['status'] = 500
            reports.append(report)
            await page.close()
        await context.close()
        # Check the actual deployed worker separately from the cold measurements.
        warm = await browser.new_context(viewport={'width':390,'height':844}, service_workers='allow')
        await warm.add_init_script('''localStorage.setItem('xyz_remember_me','true');
          localStorage.setItem('xyz_access_token',TOKEN);
          localStorage.setItem('xyz_user',JSON.stringify({id:OWNER,email:'',authenticated:true}));'''.replace('TOKEN',json.dumps(token)).replace('OWNER',json.dumps(owner)))
        await warm.route('**/*',read_only)
        page = await warm.new_page()
        report = {'library_profile':'check_cached_settings','status':500}
        try:
            await page.goto(ORIGIN+'/settings',wait_until='domcontentloaded',timeout=25000)
            await page.wait_for_function('!!navigator.serviceWorker.controller',timeout=30000)
            started = time.perf_counter()
            await page.reload(wait_until='domcontentloaded',timeout=5000)
            await page.locator('select[aria-label="Summary provider"]').wait_for(timeout=10000)
            await page.wait_for_function("!document.querySelector('select[aria-label=\"Summary provider\"]').disabled")
            report['milliseconds'] = round((time.perf_counter()-started)*1000)
            counts = await page.evaluate("(async()=>{let good=0,bad=0;for(const name of await caches.keys())if(name.startsWith('xyz-public-'))for(const request of await(await caches.open(name)).keys()){const path=new URL(request.url).pathname;if(path==='/__xyz_public_shell__'||path.startsWith('/assets/'))good++;else bad++}return [good,bad]})()")
            report['public_cache_files'], report['private_cache_files'] = counts
            if counts[0]>0 and counts[1]==0: report['status']=200
        except Exception:
            pass
        reports.append(report)
        await warm.close()
        await browser.close()
    return reports
