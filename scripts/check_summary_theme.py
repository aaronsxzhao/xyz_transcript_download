"""Rich summary rendering, theme switching and image interactions with synthetic data."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures
from scripts.check_editorial_components import CONTROL

MARKDOWN = '''# Rich summary

## Details

> A source quotation with **emphasis** and a [source link](https://example.com).

Inline `code` and [▶ 01:23](https://example.com/watch?t=83).

Screenshot-[01:23]

```python
def summarize(source):
    # Read the source before writing
    return {"title": source, "count": 42, "ready": True}
```

| Field | Explanation | Value |
| --- | --- | --- |
| Source | A long description that should remain readable on a narrow screen | Example |

![Chart description](/summary-chart.svg)

## Next section

- A readable list item
- Another item
'''

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path');parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--capture-only',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('/tmp/summary-theme-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            for width in [390,820]:
                context=await context_for(browser,width)
                task,_=fixtures();task.update(markdown=MARKDOWN,versions=[])
                await context.route('**/api/video-notes/tasks/bench*',lambda r:r.fulfill(json=task))
                await context.route('**/summary-chart.svg',lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="#e5dfd3"/><text x="60" y="200" font-size="40">Summary chart</text></svg>'))
                page=await context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}/videos/bench')
                await page.locator('[data-rendering="formatted"]').wait_for()
                await page.locator('pre').wait_for()
                for design,theme in [('classic','dark'),('editorial','light'),('editorial','dark'),('classic','light')]:
                    await choose(page,design,theme);await page.wait_for_timeout(250)
                    await page.locator('pre').scroll_into_view_if_needed()
                    await page.screenshot(path=str(args.output/f'{width}-{design}-{theme}-summary.png'))
                    result=await page.locator('pre').evaluate('e=>({bg:getComputedStyle(e.firstElementChild).backgroundColor,width:document.documentElement.scrollWidth,viewport:innerWidth})')
                    if not args.capture_only:
                        assert result['width']<=result['viewport'],result
                        expected=await page.locator('html').evaluate('e=>getComputedStyle(e).getPropertyValue("--ui-surface").trim() || "#eef2f8"')
                        if design=='editorial' or theme=='light':
                            actual=await page.locator('.summary-code').evaluate('(e,color)=>{const s=document.createElement("span");s.style.color=color;document.body.append(s);const v=getComputedStyle(s).color;s.remove();return {actual:getComputedStyle(e).backgroundColor,expected:v}}',expected)
                            assert actual['actual']==actual['expected'],actual
                            for node in await page.locator('.summary-code .token, .note-prose th, .summary-screenshot-placeholder').all():
                                colors=await node.evaluate(CONTROL)
                                assert colors['ratio']>=4.5,colors
                    await page.locator('button.reader-screenshot').first.click()
                    await page.locator('.gallery-viewport img').wait_for(state='visible')
                    await page.get_by_role('button',name='Zoom in',exact=True).click()
                    await page.get_by_role('button',name='Fit · 150%').wait_for()
                    await page.screenshot(path=str(args.output/f'{width}-{design}-{theme}-gallery.png'))
                    await page.keyboard.press('Escape');await page.locator('.screenshot-gallery').wait_for(state='hidden')
                    print(json.dumps({'width':width,'design':design,'theme':theme,'result':result}),flush=True)
                task.update(platform='web',style='original',markdown='# Article\n\n[Video source](https://www.youtube.com/watch?v=dQw4w9WgXcQ)\n\n[Source article](https://example.com/reference)')
                await context.route('https://www.youtube-nocookie.com/**',lambda r:r.fulfill(content_type='text/html',body='<p>Synthetic player</p>'))
                await page.reload();await page.locator('.article-link-card').first.wait_for()
                for design,theme in [('editorial','light'),('editorial','dark'),('classic','light')]:
                    await choose(page,design,theme);await page.wait_for_timeout(250)
                    await page.locator('.article-link-card').first.scroll_into_view_if_needed()
                    await page.screenshot(path=str(args.output/f'{width}-{design}-{theme}-article.png'))
                    if not args.capture_only:
                        for node in await page.locator('.article-link-target,.article-link-host,.article-link-action,.article-embed-button').all():
                            for state in ['default','hover','focus']:
                                if state=='hover':await node.hover()
                                if state=='focus':await node.focus()
                                colors=await node.evaluate(CONTROL)
                                assert colors['ratio']>=4.5,colors
                    await page.get_by_role('button',name='Load YouTube player',exact=True).click()
                    await page.locator('iframe.article-video-embed').wait_for()
                    await page.get_by_role('button',name='Close player',exact=True).click()
                    await page.locator('iframe.article-video-embed').wait_for(state='detached')
                assert not errors,errors
                await context.close()
            await browser.close()
    finally:server.shutdown();server.server_close()

if __name__=='__main__':asyncio.run(main())
