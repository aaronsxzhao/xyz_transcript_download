"""Synthetic browser coverage of the real verification UI; no live cookies."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_appearance import context_for,choose
from scripts.check_library_browser import serve
from playwright.async_api import async_playwright


async def main():
    server=serve(Path('web/dist').resolve())
    try:
        async with async_playwright() as p:
            browser=await p.webkit.launch() if '--webkit' in sys.argv else await p.chromium.launch(executable_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None,args=['--no-sandbox'])
            for design,theme,width in [('editorial','dark',390),('editorial','light',390),('classic','dark',320),('classic','light',820)]:
                context=await context_for(browser,width,touch=True)
                await context.route('**/api/cookies',lambda r:r.fulfill(json={'cookies':[{'platform':'youtube','has_cookie':True}]}))
                mode=['ok'];calls=[]
                async def verify(route):
                    calls.append(route.request.post_data_json)
                    await asyncio.sleep(.2)
                    success=mode[0]=='ok'
                    await route.fulfill(json={'reference':'synthetic-safe-reference','checked_at':'2026-11-03','revision':'test','cookie_present':True,'metadata_ok':True,'download_ok':success,'sample_bytes':65536 if success else 0,'elapsed_seconds':2,'stage':'complete' if success else 'media','code':mode[0],'message':'Video information and media sample verified.' if success else 'YouTube refused the media request. Refresh cookies and retry.','runtime':{'node':True,'yt-dlp':'test'}})
                await context.route('**/api/cookies/youtube/verify',verify)
                page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}/settings')
                await choose(page,design,theme)
                await page.get_by_role('button',name='Platform Accounts',exact=True).click()
                await page.get_by_role('button',name='YouTube',exact=True).click()
                panel=page.get_by_role('region',name='YouTube verification')
                await panel.wait_for()
                assert not calls, 'Opening settings must not automatically use saved cookies'
                await panel.get_by_label('YouTube video URL (optional)').fill('https://youtu.be/BaW_jenozKc')
                await panel.get_by_role('button',name='Verify connection and download',exact=True).click()
                await panel.get_by_role('button',name='Verifying…',exact=True).wait_for()
                assert await panel.get_by_role('button',name='Verifying…',exact=True).is_disabled()
                await panel.get_by_text('Media sample: passed (65536 bytes)',exact=True).wait_for()
                assert calls==[{'video_url':'https://youtu.be/BaW_jenozKc'}]
                await panel.get_by_role('button',name='Copy diagnostic report',exact=True).wait_for()
                assert await page.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
                await panel.scroll_into_view_if_needed()
                await page.screenshot(path=f'/tmp/youtube-verify-{design}-{theme}-{width}.png')
                mode[0]='forbidden'
                await panel.get_by_role('button',name='Verify connection and download',exact=True).click()
                await panel.get_by_text('Media sample: not verified',exact=True).wait_for()
                await panel.get_by_text('Video information: passed',exact=True).wait_for()
                assert not errors,errors
                print(json.dumps({'design':design,'theme':theme,'width':width,'verification_ui':'passed'}),flush=True)
                await context.close()
            await browser.close()
    finally:server.shutdown()


if __name__=='__main__':asyncio.run(main())
