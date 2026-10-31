"""Verify shipped Song-style Chinese glyphs, not just declared font families."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures

TITLE = '当你开始做自己，为什么别人会觉得你自私？｜荣格心理学'
TEXT = '中文宋体与 English 2026 混排，保留信息密度和重要限定。'


async def check(browser, origin, width, args):
    context = await context_for(browser, width)
    task, _ = fixtures()
    task.update(title=TITLE, platform='web', style='original', versions=[],
                markdown=f'# {TITLE}\n\n{TEXT}\n\n## 研究结论 Research\n\n- 外部奖励可能削弱内在动机。\n\n> 个人调节不能替代制度和平台改变。\n\n| 项目 | 说明 |\n| --- | --- |\n| 中文字体 | 宋体 |')
    entry = dict(id='bench',kind='video',content_type='article',title=TITLE,
                 source='Englisher养成计划',status='completed',platform='web',date='2026-10-30')
    await context.route('**/api/library?*', lambda r:r.fulfill(json={'items':[entry],'next_cursor':None}))
    await context.route('**/api/video-notes/tasks/bench*', lambda r:r.fulfill(json=task))
    page = await context.new_page()
    font_requests = set()
    page.on('request', lambda r:font_requests.add(r.url) if '.woff2' in r.url else None)
    errors = []
    page.on('pageerror', lambda e:errors.append(str(e)))
    try:
        await page.goto(origin + '/')
        await choose(page, 'classic', 'light')
        assert not font_requests, 'Classic must not download Editorial fonts'
        cdp = None
        if not args.webkit:
            cdp = await context.new_cdp_session(page)
            await cdp.send('DOM.enable')
            await cdp.send('CSS.enable')
        for theme in ['light', 'dark']:
            await choose(page, 'editorial', theme)
            for path, selector in [('/', '.publication-feature h2'), ('/videos/bench', '.reader-body p')]:
                await page.goto(origin + path)
                await page.locator(selector).first.wait_for()
                await page.evaluate('document.fonts.ready')
                assert await page.evaluate("[...document.fonts].some(f=>f.family.includes('Noto Serif SC')&&f.status==='loaded')"), 'The bundled Chinese font must actually load'
                selectors = [selector]
                if 'videos' in path:
                    selectors += ['.unified-header h1', '.reader-body h2', '.reader-body li', '.reader-body td', '.reader-body blockquote p']
                for target in selectors:
                    family = await page.locator(target).first.evaluate('e=>getComputedStyle(e).fontFamily')
                    assert 'Noto Serif SC' in family, (target, family)
                    if cdp:
                        await page.locator(target).first.evaluate("""e=>{
                          document.querySelector('[data-font-probe]')?.removeAttribute('data-font-probe');
                          const leaf=[e,...e.querySelectorAll('*')].find(n=>[...n.childNodes].some(t=>t.nodeType===3&&/[\u4e00-\u9fff]/.test(t.textContent)));
                          if(!leaf)throw new Error('Missing Chinese fixture text');
                          leaf.setAttribute('data-font-probe','');
                        }""")
                        root = await cdp.send('DOM.getDocument')
                        node = await cdp.send('DOM.querySelector', {'nodeId':root['root']['nodeId'], 'selector':'[data-font-probe]'})
                        fonts = (await cdp.send('CSS.getPlatformFontsForNode', {'nodeId':node['nodeId']}))['fonts']
                        assert any(f['isCustomFont'] and 'Serif' in f['familyName'] and f['glyphCount'] for f in fonts), (target, fonts)
                        assert not any('Sans' in f['familyName'] for f in fonts), (target, fonts)
                assert await page.locator('button,select,input').evaluate_all("es=>es.every(e=>getComputedStyle(e).fontFamily.includes('Noto Serif SC'))")
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                await page.locator(selector).first.scroll_into_view_if_needed()
                await page.screenshot(path=str(args.output/f'{width}-{theme}-{"reader" if "videos" in path else "dashboard"}.png'))
            await choose(page, 'classic', theme)
            assert 'Noto Serif SC' not in await page.locator('body').evaluate('e=>getComputedStyle(e).fontFamily')
        assert font_requests and all(urlparse(url).netloc == urlparse(origin).netloc for url in font_requests)
        assert len(font_requests) < 101, 'Only used Unicode subsets should load'
        assert not errors, errors
        print(json.dumps({'width':width, 'engine':'webkit' if args.webkit else 'chromium', 'font_subsets':len(font_requests), 'same_origin':True, 'checks':'passed'}), flush=True)
    finally:
        await context.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('/tmp/editorial-font-checks'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    server = serve(ROOT/'web/dist')
    try:
        async with async_playwright() as p:
            browser = await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path, args=['--no-sandbox'])
            try:
                for width in [390,1440]:
                    await check(browser, f'http://127.0.0.1:{server.server_port}', width, args)
            finally:
                await browser.close()
    finally:
        server.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
