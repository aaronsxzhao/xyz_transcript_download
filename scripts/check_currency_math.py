"""Isolated currency/math reader regression; never connects to production APIs."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright, expect
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve, fixtures

MARKDOWN = r'''## 金额与公式 / Currency and math

成本 **$100**，权利金 **$5**，目标 **$150**。

From $10 to $20; fee $5 and formula $x^2$.

Math: $2 + 2$, $100$, $$ x + y $$.

```
$100 to $5
```

Inline `$10 to $20`, escaped \$30 and \$40.
'''

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--output',type=Path,default=Path('appearance-checks/currency'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    results=[]
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=args.browser_path,chromium_sandbox=True,
                ignore_default_args=['--disable-client-side-phishing-detection','--disable-ipc-flooding-protection','--unsafely-disable-devtools-self-xss-warnings','--enable-unsafe-swiftshader'])
            for width,height in [(1440,900),(768,1024),(390,844)]:
                for design,theme in [('classic','light'),('classic','dark'),('editorial','light'),('editorial','dark')]:
                    context=await context_for(browser,width)
                    task,_=fixtures();task.update(markdown=MARKDOWN,versions=[],title='Currency and math regression',thumbnail='')
                    await context.route('**/api/video-notes/tasks/bench*',lambda r:r.fulfill(json=task))
                    page=await context.new_page();await page.set_viewport_size({'width':width,'height':height})
                    url=f'http://127.0.0.1:{server.server_port}/videos/bench'
                    await page.goto(url);await choose(page,design,theme)
                    # Reload with persisted appearance; wait for the actual optional math renderer.
                    await page.reload()
                    await expect(page.locator('article .katex')).to_have_count(4)
                    await expect(page.locator('article strong')).to_have_text(['$100','$5','$150'])
                    assert 'From $10 to $20; fee $5 and formula' in await page.locator('article').inner_text()
                    assert await page.locator('.katex-error').count()==0
                    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    await page.locator('article').scroll_into_view_if_needed()
                    await page.screenshot(path=str(args.output/f'{design}-{theme}-{width}.png'))
                    results.append({'design':design,'theme':theme,'viewport':[width,height],'currency':'PASS','formulas':4,'cold_reload':'PASS','overflow':False})
                    await context.close()
            await browser.close()
    finally:server.shutdown()
    (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({'cases':len(results),'status':'PASS'}))

if __name__=='__main__':asyncio.run(main())
