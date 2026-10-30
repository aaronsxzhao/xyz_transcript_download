"""Theme and keyboard regressions for notifications outside the page shell."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import serve
from scripts.check_editorial_components import CONTROL


async def check(browser, origin, design, theme, width, output):
    context = await context_for(browser, width)
    page = await context.new_page()
    release = asyncio.Event()
    attempts = 0
    async def response(route):
        nonlocal attempts
        if route.request.method == 'POST':
            attempts += 1
            await release.wait()
            if attempts == 1:
                await route.fulfill(status=400, json={'detail': 'Cannot load this podcast. Please retry.'})
            else:
                await route.fulfill(json={'pid':'new','title':'New podcast','author':'Author','description':'Description','platform':'xiaoyuzhou','episode_count':0})
        else:
            await route.fulfill(json=[])
    await context.route('**/api/podcasts', response)
    await context.route('**/api/podcasts?*', response)

    async def inspect(kind, title, dismiss=True):
        toast = page.locator('.toast-stack>div').filter(has_text=title)
        await toast.wait_for()
        await page.wait_for_timeout(400)  # Entrance animation must finish before capture.
        await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{kind}.png'))
        if design == 'editorial':
            assert await toast.evaluate("e=>{const p=document.createElement('span');p.style.background='var(--ui-surface)';e.append(p);const expected=getComputedStyle(p).backgroundColor;p.remove();return getComputedStyle(e).backgroundColor===expected}"), 'Notification retains Classic surface'
            assert await toast.evaluate("e=>getComputedStyle(e).borderRadius===getComputedStyle(document.documentElement).getPropertyValue('--ui-radius').trim()")
        for text in await toast.locator('p').all():
            assert (await text.evaluate(CONTROL))['ratio'] >= 4.5, (design,theme,kind,'text')
        assert (await toast.locator(':scope>svg').evaluate(CONTROL))['ratio'] >= 3, (design,theme,kind,'icon')
        close = toast.get_by_role('button')
        await close.hover()
        await page.wait_for_timeout(200)
        assert (await close.evaluate(CONTROL))['ratio'] >= 3
        await close.focus()
        await page.keyboard.press('Shift+Tab')
        await page.keyboard.press('Tab')
        assert await close.evaluate('e=>e===document.activeElement')
        assert await close.evaluate("e=>getComputedStyle(e).outlineStyle!=='none'")
        bounds = await toast.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
        await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{kind}.png'))
        if dismiss:
            await page.keyboard.press('Enter')
            await toast.wait_for(state='detached')

    try:
        await page.goto(origin + '/podcasts')
        await choose(page, design, theme)
        await page.wait_for_timeout(400)
        await page.keyboard.press('Tab')
        search = page.get_by_role('textbox', name='Search podcasts', exact=True)
        await search.focus()
        assert await search.evaluate("e=>e.matches(':focus-visible')")
        assert (await search.evaluate(CONTROL))['outlineRatio'] >= 3, (design,theme,'search focus')
        await page.screenshot(path=str(output/f'{design}-{theme}-{width}-focus.png'))
        await page.get_by_role('button', name='Check podcast updates', exact=True).click()
        await inspect('info', 'No update sources')
        await page.get_by_role('button', name='Add Podcast', exact=True).click()
        await page.get_by_label('Podcast URL', exact=True).fill('https://example.test/feed.xml')
        await page.get_by_role('button', name='Add', exact=True).click()
        await inspect('loading', 'Adding podcast...', dismiss=False)
        release.set()
        await inspect('error', 'Failed to add podcast')
        assert await page.get_by_label('Podcast URL', exact=True).input_value() == 'https://example.test/feed.xml'
        await page.get_by_role('button', name='Add', exact=True).click()
        await inspect('success', 'Podcast added')
        print(json.dumps({'design':design,'theme':theme,'width':width,'feedback':'passed'}),flush=True)
    finally:
        release.set()
        await context.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('/tmp/global-feedback'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    server = serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser = await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for design in ['classic','editorial']:
                    for theme in ['light','dark']:
                        for width in [320,820]:
                            await check(browser,f'http://127.0.0.1:{server.server_port}',design,theme,width,args.output)
            finally:
                await browser.close()
    finally:
        server.shutdown();server.server_close()

if __name__ == '__main__':
    asyncio.run(main())
