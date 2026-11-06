import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).parent;results=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True,proxy={'server':os.environ['HTTPS_PROXY']})
 c=b.new_context(ignore_https_errors=False,viewport={'width':390,'height':844})
 c.route('**/*',lambda r:r.continue_() if r.request.method in ['GET','HEAD','OPTIONS'] else r.abort())
 page=c.new_page();page.goto('https://aipodcastsummary.online/login',wait_until='networkidle')
 page.get_by_label('Email',exact=True).fill('fixture@example.com')
 page.get_by_label('Email',exact=True).press('Tab')
 assert page.get_by_label('Password',exact=True).evaluate('(e)=>e===document.activeElement')
 page.locator('summary[aria-label="Appearance settings"]').click()
 page.locator('[aria-label="Switch to light mode"]').click()
 assert page.get_by_label('Email',exact=True).input_value()=='fixture@example.com'
 page.locator('[aria-label="Switch to dark mode"]').wait_for()
 page.locator('summary[aria-label="Appearance settings"]').click()
 page.get_by_label('Password',exact=True).focus()
 page.screenshot(path=str(out/'login-light-stable.png'))
 page.reload(wait_until='networkidle');assert page.locator('[aria-label="Switch to dark mode"]').count()==1
 results.append({'chain':'keyboard focus → light theme → draft retained → reload theme retained','status':'PASS'})
 page.get_by_role('button',name='Forgot password?',exact=True).click()
 page.get_by_label('Email',exact=True).fill('invalid')
 page.get_by_role('button',name='Send recovery link',exact=True).click()
 assert not page.get_by_label('Email',exact=True).evaluate('(e)=>e.validity.valid')
 page.get_by_label('Email',exact=True).fill('fixture@example.com')
 assert page.get_by_label('Email',exact=True).evaluate('(e)=>e.validity.valid')
 page.screenshot(path=str(out/'recovery-light-corrected.png'))
 page.get_by_role('button',name='Back to sign in',exact=True).click()
 assert page.get_by_role('button',name='Sign In',exact=True).is_visible()
 results.append({'chain':'recovery → invalid email native validation → correct without submitting → return sign-in','status':'PASS'})
 page.get_by_role('button',name='Sign up',exact=True).click()
 assert page.get_by_label('Confirm Password',exact=True).is_visible()
 page.get_by_role('button',name='Sign in',exact=True).click()
 assert page.get_by_role('button',name='Sign In',exact=True).is_visible()
 results.append({'chain':'sign-in → sign-up → confirm-password field → return sign-in','status':'PASS'})
 b.close()
(out/'forms-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
