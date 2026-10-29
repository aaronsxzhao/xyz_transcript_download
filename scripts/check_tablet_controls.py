"""Synthetic touch/Safari control geometry and constrained video-card checks."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for, choose
from scripts.check_library_browser import fixtures, serve


async def check(browser, origin, width, output):
    context = await context_for(browser, width, touch=True)
    task, _ = fixtures()
    task.update(title='【熟肉】我把 GPT-6 Astra 变成全天候股票交易员，重新理解长期投资与判断',
                channel='Synthetic channel', versions=[], thumbnail='https://fixture.test/art.svg')
    await context.route('**/api/video-notes/tasks/by-channel*', lambda route: route.fulfill(json={'tasks':[task],'next_cursor':None}))
    artwork = (Path(__file__).resolve().parents[1]/'design-review/appearance/fixtures/post.jpg').read_bytes()
    await context.route('**/api/image-proxy**', lambda route: route.fulfill(content_type='image/jpeg', body=artwork))
    page = await context.new_page()
    try:
        await page.goto(origin+'/videos?platform=youtube&channel=Synthetic%20channel')
        await page.locator('.video-task-list h3').wait_for()
        await page.locator('.video-thumbnail[data-image-state=ready]').wait_for()
        for design in ['classic','editorial']:
            for theme in ['dark','light']:
                await choose(page, design, theme)
                await page.wait_for_timeout(200)  # Compare settled colors after the 150ms transition.
                metrics = await page.evaluate('''() => {
                  const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}};
                  const card=document.querySelector('.video-task-content'),nav=document.querySelector('.navigation-toggle');
                  return {select:box(document.querySelector('.appearance-controls select')),button:box(document.querySelector('.appearance-controls button')),
                    radius:getComputedStyle(document.documentElement).getPropertyValue('--ui-radius').trim(),
                    controls:[...document.querySelectorAll('.appearance-controls select,.appearance-controls button,.video-task-list .collection-actions>.ui-button,.video-task-list .task-more>summary')].map(e=>({radius:getComputedStyle(e).borderTopLeftRadius,border:getComputedStyle(e).borderTopWidth})),
                    secondary:[...card.querySelectorAll('.collection-actions>.ui-button:not(.ui-button-primary),.task-more>summary')].map(e=>{const c=getComputedStyle(e);return [c.backgroundColor,c.borderColor,c.fontSize,c.lineHeight]}),
                    artwork:box(card.querySelector('.video-thumbnail')),fit:getComputedStyle(card.querySelector('.video-thumbnail img')).objectFit,
                    menu:box(nav),card:box(card),title:box(card.querySelector('h3')),actions:box(card.querySelector('.collection-actions')),
                    lastAction:box(card.querySelector('.collection-actions').lastElementChild),
                    container:document.querySelector('.video-task-list').clientWidth,
                    overflow:document.documentElement.scrollWidth>innerWidth+1||document.querySelector('main').scrollWidth>document.querySelector('main').clientWidth+1,
                    obscured:[...document.querySelectorAll('header a,header button,header select')].filter(e=>{
                      const r=e.getBoundingClientRect();return r.width&&r.height&&!e.disabled&&(r.x<0||r.right>innerWidth+1||!e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)))
                    }).map(e=>e.getAttribute('aria-label')||e.textContent)};
                }''')
                assert metrics['select']['height'] == metrics['button']['height'] == 44, (width,design,theme,metrics)
                if metrics['menu']['width']:
                    assert metrics['menu']['height'] == metrics['button']['height']
                assert all(c['radius'] == metrics['radius'] and c['border'] == '1px' for c in metrics['controls']), (width,design,theme,'inconsistent controls',metrics)
                assert all(c == metrics['secondary'][0] for c in metrics['secondary']), (width,design,theme,'inconsistent secondary button styles',metrics)
                assert abs(metrics['lastAction']['x']+metrics['lastAction']['width']-metrics['actions']['x']-metrics['actions']['width']) < 1, (width,design,theme,'actions not right aligned',metrics)
                assert metrics['fit'] == 'contain', (width,design,theme,'cropped artwork')
                assert not metrics['overflow'] and not metrics['obscured'], (width,design,theme,metrics)
                if 600 <= metrics['container'] <= 1000:
                    assert abs(metrics['artwork']['y']+metrics['artwork']['height']/2-metrics['card']['y']-metrics['card']['height']/2) < 1, (width,design,theme,'artwork not centered across rows',metrics)
                    assert metrics['title']['width'] >= metrics['card']['width']*.6, (width,design,theme,'squeezed title',metrics)
                    assert metrics['actions']['y'] >= metrics['title']['bottom'], (width,design,theme,'actions beside title',metrics)
                if width == 820 and design == 'editorial' and theme == 'light':
                    await page.wait_for_timeout(250)  # Let the background-color transition finish.
                    await page.screenshot(path=str(output/'tablet-editorial.png'), full_page=True)
                    await page.locator('.publication-nav').screenshot(path=str(output/'tablet-controls.png'))
                    await page.locator('.video-task-list').screenshot(path=str(output/'tablet-card.png'))
                print(json.dumps({'width':width,'design':design,'theme':theme,'title_width':metrics['title']['width'],'control_height':44}),flush=True)
        # The More disclosure and source link remain separate from card navigation.
        more = page.locator('.video-task-list .task-more summary').first
        await more.click()
        assert '/videos?' in page.url, 'More unexpectedly navigated into the reader'
        assert await page.locator('.video-task-list .task-more[open]').count() == 1
        await page.locator('h1').click()
        assert await page.locator('.task-more[open]').count() == 0, 'Outside click did not dismiss More'
        await more.click()
        await page.keyboard.press('Escape')
        assert await page.locator('.task-more[open]').count() == 0
        assert await more.evaluate('(e)=>e===document.activeElement')
        await more.click()
        await page.get_by_role('combobox', name='Interface style').focus()
        assert await page.locator('.task-more[open]').count() == 0, 'Focus leaving the menu did not dismiss More'
        await page.get_by_role('link',name='View',exact=True).click()
        await page.wait_for_url('**/videos/bench')
    except Exception:
        await page.screenshot(path=str(output/f'failure-{width}.png'), full_page=True)
        raise
    finally:
        await context.close()


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--widths',nargs='+',type=int,default=[320,390,640,744,768,820,834,1024,1180,1366])
    parser.add_argument('--output',type=Path,default=Path('appearance-checks/tablet'))
    args=parser.parse_args();args.output /= 'webkit' if args.webkit else 'chromium';args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for width in args.widths:
                    await check(browser,f'http://127.0.0.1:{server.server_port}',width,args.output)
            finally:
                await browser.close()
    finally:
        server.shutdown();server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
