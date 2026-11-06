import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).parent
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']})
 c=b.new_context(ignore_https_errors=False,viewport={'width':390,'height':844})
 c.route('**/*',lambda r:r.continue_() if r.request.method in ['GET','HEAD','OPTIONS'] else r.abort())
 page=c.new_page();page.goto('https://aipodcastsummary.online/login',wait_until='networkidle')
 print('initial',page.locator('body').inner_text())
 print('controls',page.locator('button').evaluate_all('(es)=>es.map(e=>({text:e.innerText,label:e.getAttribute("aria-label"),title:e.getAttribute("title")}))'))
 page.get_by_role('button',name='Forgot password?',exact=True).click()
 print('recovery',page.locator('body').inner_text())
 page.screenshot(path=str(out/'recovery-mobile.png'))
 page.get_by_role('button',name='Back to sign in',exact=True).click()
 page.get_by_role('button',name='Sign up',exact=True).click()
 print('signup',page.locator('body').inner_text())
 page.screenshot(path=str(out/'signup-mobile.png'))
 b.close()
