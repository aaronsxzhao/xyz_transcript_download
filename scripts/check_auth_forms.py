"""Synthetic authentication form concurrency, retry and feedback checks; no live writes."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for
from scripts.check_library_browser import serve

async def check(browser, origin, width, design, theme, output):
    for mode in ['signin', 'signup', 'recovery', 'reset']:
        context = await context_for(browser, width, authenticated=False)
        await context.add_init_script("localStorage.setItem('xyz:design',"+json.dumps(design)+");localStorage.setItem('xyz:color-theme',"+json.dumps(theme)+");")
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        release = asyncio.Event()
        started = asyncio.Event()
        requests = []
        endpoint = {'signin':'signin','signup':'signup','recovery':'password-reset','reset':'password'}[mode]
        async def request(route):
            requests.append(route.request.post_data_json)
            started.set()
            await release.wait()
            if len(requests) == 1 or mode == 'signin':
                await route.fulfill(status=503, json={'detail':'Synthetic service unavailable. Please retry.'})
            else:
                await route.fulfill(json={'message':'Check your email for a recovery link.'})
        await context.route('**/api/auth/'+endpoint, request)
        try:
            if mode == 'reset':
                await page.goto(origin+'/reset-password#type=recovery&access_token=synthetic-recovery')
                await page.get_by_label('New password',exact=True).fill('synthetic-password')
                await page.get_by_label('Confirm password',exact=True).fill('synthetic-password')
                submit = 'Set new password'
            else:
                await page.goto(origin+'/login'+('?mode=recovery' if mode=='recovery' else ''))
                if mode == 'signup': await page.get_by_role('button',name='Sign up',exact=True).click()
                await page.get_by_label('Email',exact=True).fill('fixture@example.com')
                if mode != 'recovery': await page.get_by_label('Password',exact=True).fill('synthetic-password')
                if mode == 'signup': await page.get_by_label('Confirm Password',exact=True).fill('synthetic-password')
                submit = {'signin':'Sign In','signup':'Create Account','recovery':'Send recovery link'}[mode]
            await page.get_by_role('button',name=submit,exact=True).click()
            await page.locator('form[aria-busy=true]').wait_for()
            await asyncio.wait_for(started.wait(), timeout=10)
            assert await page.locator('form input:enabled').count() == 0, (mode,'editable pending fields')
            # A second submit event while waiting must not start a second request.
            await page.locator('form').dispatch_event('submit')
            await page.wait_for_timeout(150)
            assert len(requests) == 1, (mode,'duplicate submission',requests)
            if mode != 'reset':
                switches = page.locator('.auth-page button').filter(has_text='Forgot password?').or_(page.get_by_role('button',name='Back to sign in',exact=True)).or_(page.get_by_role('button',name='Sign up',exact=True)).or_(page.get_by_role('button',name='Sign in',exact=True))
                for button in await switches.all(): assert await button.is_disabled()
            await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{mode}-pending.png'))
            release.set()
            await page.get_by_role('alert').filter(has_text='Synthetic service unavailable').wait_for()
            assert await page.locator('form').get_attribute('aria-busy') == 'false'
            assert await page.get_by_role('button',name=submit,exact=True).is_enabled()
            if mode != 'reset': assert await page.get_by_label('Email',exact=True).input_value() == 'fixture@example.com'
            if mode != 'recovery': assert await page.get_by_label('New password' if mode=='reset' else 'Password',exact=True).input_value() == 'synthetic-password'
            await page.get_by_role('button',name=submit,exact=True).click()
            if mode == 'signin': await page.get_by_role('alert').wait_for()
            else: await page.get_by_role('status').filter(has_text='email' if mode!='reset' else 'password is updated').wait_for()
            assert len(requests) == 2, (mode,'retry did not run')
            if theme == 'light' and mode != 'reset':
                contrast = await page.locator('.auth-feedback p').evaluate(r'''e => {
                    const rgb = color => color.match(/[\d.]+/g).map(Number);
                    const light = color => {const v=color.slice(0,3).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};
                    const layers=[];for(let el=e;el;el=el.parentElement)layers.unshift(rgb(getComputedStyle(el).backgroundColor));
                    let background=[255,255,255];for(const c of layers){const a=c[3]??1;background=background.map((v,i)=>c[i]*a+v*(1-a))}
                    const a=light(rgb(getComputedStyle(e).color)),b=light(background);
                    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                }''')
                assert contrast >= 4.5, (design,theme,mode,'Unreadable feedback',contrast)
            await page.wait_for_timeout(200)
            await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{mode}-result.png'))
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            assert not errors, errors
            print(json.dumps({'width':width,'design':design,'theme':theme,'mode':mode,'pending_retry_feedback':'passed'}),flush=True)
        except Exception:
            await page.screenshot(path=str(output/f'{design}-{theme}-{width}-{mode}-failure.png'))
            raise
        finally:
            release.set()
            await context.close()
    context = await context_for(browser,width,authenticated=False)
    page = await context.new_page()
    await page.goto(origin+'/reset-password')
    await page.get_by_role('link',name='Request a new recovery link',exact=True).click()
    await page.get_by_role('button',name='Send recovery link',exact=True).wait_for()
    await context.close()

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-path')
    parser.add_argument('--webkit',action='store_true')
    parser.add_argument('--widths',type=int,nargs='+',default=[390,820])
    parser.add_argument('--output',type=Path,default=Path('/tmp/auth-form-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=serve(Path(__file__).resolve().parents[1]/'web/dist')
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if args.webkit else await p.chromium.launch(executable_path=args.browser_path,args=['--no-sandbox'])
            try:
                for width in args.widths:
                    for design in ['classic','editorial']:
                        for theme in ['dark','light']:
                            await check(browser,f'http://127.0.0.1:{server.server_port}',width,design,theme,args.output)
            finally: await browser.close()
    finally: server.shutdown();server.server_close()

if __name__=='__main__': asyncio.run(main())
