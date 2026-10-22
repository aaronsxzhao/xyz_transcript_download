"""Reader layout under late images, ultra-wide screens and failed optional JS.

Only synthetic content is used; screenshots can be safely inspected locally.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import fixtures, serve
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


async def check(browser, origin, width, blocked, output):
    task, summary = fixtures()
    task['markdown'] = '''# 交易 **复盘**

## 目录
- [趋势](#趋势)

---

## 趋势 — 判断

**确认市场结构**后再执行计划。

![横向图](/data/screenshots/wide.svg)

| 信号 | 行动 |
| --- | --- |
| 突破 | 等待确认 |

## 趋势 — 判断

- 控制风险
  - 等待信号

![纵向图](/data/screenshots/portrait.svg)

![小图](/data/screenshots/small.svg)
'''
    summary['key_points'] = [{'topic': f'主题 {i:02}', 'summary': '**重点**：' + ('结合市场背景判断。' * (70 if i == 0 else 3)), 'original_quote': '', 'timestamp': ''} for i in range(15)]
    summary['topics'] = [point['topic'] for point in summary['key_points']]
    context = await browser.new_context(viewport={'width': width, 'height': 1000}, service_workers='block')
    await context.add_init_script('''if(location.protocol==='http:'){
      localStorage.setItem('xyz_access_token',TOKEN);
      localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
      window.WebSocket=class{static OPEN=1;readyState=0;send(){}close(){}};
    }'''.replace('TOKEN', json.dumps(token(int(time.time()) + 3600))))
    page = await context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    async def api(route):
        path = urlparse(route.request.url).path
        body = {'supabase_enabled': True} if path == '/api/auth/config' else {}
        if path == '/api/auth/me': body = {'id': 'bench', 'email': 'bench@example.com', 'authenticated': True}
        if path == '/api/video-notes/tasks/bench': body = task
        if path == '/api/summaries/bench': body = summary
        await route.fulfill(body=json.dumps(body), content_type='application/json')
    async def image(route):
        path = urlparse(route.request.url).path
        w, h = (800, 1600) if 'portrait' in path else (320, 180) if 'small' in path else (1920, 1080)
        await asyncio.sleep(.5)
        await route.fulfill(content_type='image/svg+xml', body=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="#1e3a5f"/><text x="20" y="50" fill="white" font-size="22">Synthetic chart {w} × {h}</text></svg>')
    await page.route('**/api/**', api)
    await page.route('**/data/screenshots/**', image)
    if blocked:
        await page.route('**/assets/**', lambda route: route.fulfill(status=503, body='Optional formatter unavailable', content_type='application/javascript') if urlparse(route.request.url).path.endswith('.js') else route.continue_())
    try:
        await page.goto(origin + '/videos/bench')
        article = page.locator('article[data-rendering="' + ('plain' if blocked else 'formatted') + '"]')
        await article.wait_for()
        assert await article.locator('h1 strong').inner_text() == '复盘'
        assert await article.locator('h2').count() == 2
        assert await article.locator('table tbody td').first.inner_text() == '突破'
        assert await article.locator('li li').count() == 1
        assert await article.locator('h2').evaluate_all('(nodes)=>nodes.map(n=>n.id)') == ['趋势-判断', '趋势-判断-1']
        await article.locator('img').first.wait_for()
        for img in await article.locator('img').element_handles():
            await img.scroll_into_view_if_needed()
            await page.wait_for_function('(img)=>img.naturalWidth>0', arg=img)
        images = await article.locator('img').evaluate_all('nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {width:r.width,height:r.height,natural:n.naturalWidth}})')
        assert len(images) == 3, images
        assert all(i['width'] <= 761 and i['height'] <= 421 and i['width'] <= i['natural']+2.1 for i in images), images
        await article.locator('button.reader-screenshot').first.click()
        await page.get_by_role('dialog').wait_for()
        await page.keyboard.press('Escape')
        assert not await page.get_by_role('dialog').count()
        await page.locator('main').evaluate('(node)=>node.scrollTop=0')
        await page.screenshot(path=str(output / f'video-{width}-{"fallback" if blocked else "rich"}.png'))
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
        if width >= 1280:
            # Contents must target the same heading IDs in both renderers.
            toc = page.locator('aside').get_by_text('趋势 — 判断', exact=True)
            assert await toc.count() == 2
            await toc.last.click()
            await page.wait_for_timeout(100)
            assert await page.locator('main').evaluate('(node)=>node.scrollTop') > 0
        await page.goto(origin + '/viewer/bench')
        await page.locator('[data-topic-card]').first.wait_for()
        await page.locator('[data-topic-card] button').nth(8).click()
        assert await page.locator('[data-topic-column]').count() == 1
        cards = await page.locator('[data-topic-card]').evaluate_all('(nodes)=>nodes.map(n=>{const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,width:r.width}})')
        assert all(abs(card['left']-cards[0]['left']) < 1 and abs(card['width']-cards[0]['width']) < 1 for card in cards)
        assert all(0 <= card['top']-cards[i]['bottom'] <= 17 for i, card in enumerate(cards[1:])), cards
        labels = await page.locator('[data-topic-card] button').evaluate_all('(nodes)=>nodes.map(n=>n.textContent)')
        assert all(f'主题 {i:02}' in text for i, text in enumerate(labels))
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
        assert not errors, errors
        await page.screenshot(path=str(output / f'podcast-{width}.png'))
        return {'width': width, 'optional_js_blocked': blocked, 'bounded_images': images, 'topic_cards': 15, 'js_errors': len(errors)}
    finally:
        await context.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-path'); parser.add_argument('--browser-args', type=Path)
    parser.add_argument('--webkit', action='store_true'); parser.add_argument('--output', type=Path, default=Path('/tmp/xyz-reader-layout'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    server = serve(Path(__file__).resolve().parents[1] / 'web/dist')
    try:
        async with async_playwright() as p:
            for width in [390, 1440, 2560, 5120]:
                for blocked in [False, True]:
                    browser = await p.chromium.launch(executable_path=args.browser_path, headless=True, args=json.loads(args.browser_args.read_text()) if args.browser_args else ['--no-sandbox'])
                    print(json.dumps(await check(browser, f'http://127.0.0.1:{server.server_port}', width, blocked, args.output)), flush=True)
                    await browser.close()
            if args.webkit:
                for blocked in [False, True]:
                    browser = await p.webkit.launch(headless=True)
                    print(json.dumps(await check(browser, f'http://127.0.0.1:{server.server_port}', 1440, blocked, args.output)), flush=True)
                    await browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__': asyncio.run(main())
