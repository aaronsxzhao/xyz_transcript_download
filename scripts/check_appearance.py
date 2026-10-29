"""Production appearance/state regressions with synthetic data; no account writes."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve, fixtures
from scripts.check_page_loading import token
from playwright.async_api import async_playwright


READER_CONTRAST = r'''() => {
                  const luminance = color => {
                    const rgb=color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
                    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
                  };
                  return [...document.querySelectorAll('.reader-body :is(h1,h2,h3,h4,h5,h6,strong)')].map(e=>{
                    let bg=e;while(bg.parentElement&&getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)')bg=bg.parentElement;
                    const a=luminance(getComputedStyle(e).color),b=luminance(getComputedStyle(bg).backgroundColor);
                    return {text:e.textContent,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
                  });
                }'''

async def context_for(browser, width, authenticated=True, touch=False):
    context = await browser.new_context(viewport={'width': width, 'height': 900}, service_workers='block', has_touch=touch)
    if authenticated:
        await context.add_init_script("""
          localStorage.setItem('xyz_remember_me','true');
          localStorage.setItem('xyz_access_token',TOKEN);
          localStorage.setItem('xyz_user',JSON.stringify({id:'bench',email:'bench@example.com',authenticated:true}));
          window.WebSocket=class {static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}
            send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})}),1)}close(){}}
        """.replace('TOKEN', json.dumps(token(int(time.time()) + 7200))))
    task, summary = fixtures()
    task.update(versions=[], markdown='# Synthetic note\n\nA readable paragraph.\n\n> A quote with its original spacing.\n\n## Next section\n\nFinal paragraph.\n\n### Third\n\n#### Fourth\n\n##### Fifth\n\n###### Sixth\n\n**Emphasis**.')
    entry = {'id':'bench','kind':'video','content_type':'video','title':'Synthetic video','source':'Synthetic source',
             'status':'completed','platform':'youtube','date':'2026-10-29','thumbnail':''}
    async def api(route):
        path = urlparse(route.request.url).path
        body = {}
        if path == '/api/auth/config': body = {'supabase_enabled':True}
        elif path == '/api/auth/me':
            if not authenticated:
                await route.fulfill(status=401, json={'detail':'Sign in required'})
                return
            body = {'id':'bench','email':'bench@example.com','authenticated':True}
        elif path == '/api/settings':
            body = {'whisper_mode':'api','whisper_model':'whisper-large-v3','llm_provider':'groq',
                    'llm_model':'openai/gpt-oss-120b','check_interval':3600,'groq_available':True}
        elif path == '/api/stats': body = {key:3 for key in ['total_podcasts','total_episodes','total_transcripts','total_summaries','total_video_channels','total_videos','completed_videos']}
        elif path == '/api/library': body = {'items':[entry],'next_cursor':None}
        elif path == '/api/library/sources': body = {'sources':['Synthetic source'],'next_cursor':None}
        elif path == '/api/podcasts': body = [{'pid':'show','title':'Synthetic podcast','platform':'xiaoyuzhou','cover_url':'','episode_count':3,'summarized_count':1}]
        elif path == '/api/cookies': body = {'cookies':[]}
        elif path == '/api/truncated': body = {'truncated':[]}
        elif path == '/api/podcasts/show': body = {'pid':'show','title':'Synthetic podcast','platform':'xiaoyuzhou','episode_count':1}
        elif path == '/api/podcasts/content': body = [{'eid':'bench','pid':'show','title':'Synthetic episode','duration':1200,'has_summary':True,'has_transcript':True}]
        elif path == '/api/jobs': body = {'jobs':[]}
        elif path == '/api/content-updates': body = {'items':[]}
        elif path == '/api/video-notes/tasks/bench': body = task
        elif path == '/api/video-notes/tasks/bench/transcript': body = {'transcript':task['transcript']}
        elif path == '/api/summaries/bench': body = summary
        elif path == '/api/transcripts/bench': body = {**task['transcript'],'episode_id':'bench','language':'en'}
        elif path == '/api/summaries/recent': body = []
        elif path == '/api/video-notes/channels': body = {'channels':[]}
        elif path.startswith('/api/video-notes/'): body = {'tasks':[]}
        await route.fulfill(json=body)
    await context.route('**/api/**', api)
    return context


async def choose(page, design, theme):
    await page.get_by_role('combobox', name='Interface style').select_option(design)
    await page.wait_for_function('(d)=>document.documentElement.dataset.design===d', arg=design)
    if await page.locator('html').get_attribute('data-theme') != theme:
        await page.get_by_role('button', name=f'Switch to {theme} mode').click()
    await page.wait_for_function('(t)=>document.documentElement.dataset.theme===t', arg=theme)


async def geometry(page):
    return await page.evaluate("""() => Object.fromEntries(['h1','.dashboard-workspace','.dashboard-recent','.reader-body','form'].flatMap(s=>{
      const e=document.querySelector(s);if(!e)return [];const r=e.getBoundingClientRect(),c=getComputedStyle(e);
      return [[s,[r.x,r.y,r.width,r.height,c.fontSize,c.color]]];
    }))""")


async def check(browser, origin, width):
    context = await context_for(browser, width)
    page = await context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    routes = ['/', '/library', '/settings', '/podcasts?platform=xiaoyuzhou', '/podcasts/show/episodes', '/videos', '/videos/bench', '/viewer/bench']
    for path in routes:
        await page.goto(origin + path)
        await page.get_by_role('combobox', name='Interface style').wait_for()
        await page.locator('h1').first.wait_for()
        if path in ['/videos/bench', '/viewer/bench']:
            await page.locator('.reader-body').wait_for()
        if path == '/videos/bench':
            await page.locator('[data-rendering="formatted"]').wait_for()
        await page.wait_for_timeout(250)
        await choose(page, 'classic', 'dark')
        baseline = await geometry(page)
        draft = None
        if path == '/settings':
            draft = page.locator('select').filter(has=page.locator('option[value="custom"]')).first
            await draft.select_option('custom')
            await page.get_by_text('Unsaved changes', exact=True).wait_for()
            baseline = await geometry(page)
        for design, theme in [('editorial','dark'), ('editorial','light'), ('classic','light'), ('classic','dark')]:
            await choose(page, design, theme)
            assert not await page.evaluate("""() => document.documentElement.scrollWidth>innerWidth+1 ||
              [...document.querySelectorAll('.app-shell>main')].some(e=>e.scrollWidth>e.clientWidth+1)"""), (width,path,design,theme,'overflow')
            if path == '/videos/bench':
                await page.wait_for_timeout(200)
                contrast = await page.evaluate(READER_CONTRAST)
                assert contrast and all(c['ratio'] >= 4.5 for c in contrast), (width,design,theme,'heading contrast',contrast)
            if design == 'classic':
                assert not await page.locator('.publication-feature').count()
            if draft:
                assert await draft.input_value() == 'custom', (width,'settings draft lost')
        assert await geometry(page) == baseline, (width,path,'Classic layout changed after round trip')
        if path == '/':
            await page.get_by_role('button', name='Articles', exact=True).click()
            await choose(page, 'editorial', 'light')
            await choose(page, 'classic', 'dark')
            assert await page.get_by_role('button', name='Articles', exact=True).get_attribute('aria-pressed') == 'true'
        if path == '/settings':
            for tab in ['Platform Accounts', 'Tools & Data', 'General']:
                button = page.get_by_role('button', name=tab, exact=True)
                await button.click()
                assert await button.get_attribute('aria-pressed') == 'true'
                assert await page.get_by_role('button', pressed=True).filter(has_text=tab).count() == 1
            assert await draft.input_value() == 'custom', 'Draft lost when changing settings sections'
            assert await page.get_by_label('Integration Token', exact=True).count() == 1
        print(json.dumps({'width':width,'path':path,'appearances':4,'round_trip':'passed'}), flush=True)
    await page.goto(origin + '/library')
    await choose(page, 'editorial', 'light')
    await page.reload()
    await page.get_by_role('combobox', name='Interface style').wait_for()
    assert await page.locator('html').get_attribute('data-design') == 'editorial'
    assert await page.locator('html').get_attribute('data-theme') == 'light'
    other = await context.new_page()
    await other.goto(origin + '/library')
    await other.get_by_role('combobox', name='Interface style').wait_for()
    await choose(page, 'classic', 'dark')
    await other.wait_for_function("()=>document.documentElement.dataset.design==='classic' && document.documentElement.dataset.theme==='dark'")
    assert not errors, errors
    await context.close()

    context = await context_for(browser, width, authenticated=False)
    page = await context.new_page()
    await page.goto(origin + '/login')
    await page.get_by_label('Email', exact=True).fill('reader@example.com')
    await page.get_by_label('Password', exact=True).fill('synthetic-password')
    baseline = await geometry(page)
    entry = page.get_by_label('Appearance settings', exact=True)
    await entry.click()
    await choose(page, 'editorial', 'light')
    await choose(page, 'classic', 'dark')
    await page.keyboard.press('Escape')
    assert await entry.evaluate('(e)=>e===document.activeElement')
    assert await page.get_by_label('Email', exact=True).input_value() == 'reader@example.com'
    assert await page.get_by_label('Password', exact=True).input_value() == 'synthetic-password'
    assert await geometry(page) == baseline, (width,'auth layout changed')
    await context.close()
    print(json.dumps({'width':width,'auth_draft_focus_layout':'passed'}), flush=True)


async def check_failure(browser, origin):
    for mode in ['blocked', 'stalled-switch', 'stalled-startup']:
        context = await context_for(browser, 390)
        seen = []
        release = asyncio.Event()
        async def reject(route):
            seen.append(route.request.url)
            if mode != 'blocked':
                await release.wait()
            await route.abort()
        await context.route('**/assets/editorial-*.css', reject)
        if mode == 'stalled-startup':
            await context.add_init_script("localStorage.setItem('xyz:design','editorial')")
        page = await context.new_page()
        try:
            await page.goto(origin + '/', wait_until='domcontentloaded')
            if mode != 'stalled-startup':
                await page.get_by_role('combobox', name='Interface style').select_option('editorial')
                await page.get_by_role('alert').filter(has_text='Reload to retry').wait_for(timeout=12000)
            else:
                await page.get_by_role('combobox', name='Interface style').wait_for(timeout=12000)
            assert seen, 'Failure check must intercept the actual stylesheet'
            assert await page.locator('html').get_attribute('data-design') == 'classic'
            assert await page.get_by_role('combobox', name='Interface style').is_enabled()
        finally:
            release.set()
            # Let the held request finish before disposing the route context.
            await page.wait_for_timeout(50)
        await context.close()
        print(json.dumps({mode:'keeps usable Classic'}), flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('appearance-checks'))
    parser.add_argument('--widths', type=int, nargs='+', default=[390,1440])
    args = parser.parse_args()
    server = serve(Path(__file__).resolve().parents[1] / 'web/dist')
    try:
        async with async_playwright() as p:
            browser = await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path, args=['--no-sandbox'])
            try:
                for width in args.widths:
                    await check(browser, f'http://127.0.0.1:{server.server_port}', width)
                await check_failure(browser, f'http://127.0.0.1:{server.server_port}')
            except Exception:
                args.output.mkdir(parents=True, exist_ok=True)
                engine = 'webkit' if args.webkit else 'chromium'
                for index, context in enumerate(browser.contexts):
                    for tab, page in enumerate(context.pages):
                        try:
                            await page.screenshot(path=str(args.output / f'{engine}-{index}-{tab}-failure.png'), full_page=True)
                        except Exception:
                            pass
                raise
            finally:
                await browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
