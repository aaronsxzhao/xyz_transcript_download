"""Approved Nov 15 design fixes against a production build; synthetic data only."""
import argparse,asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from scripts.check_appearance import context_for
from scripts.check_library_browser import serve,fixtures

async def main():
 p=argparse.ArgumentParser();p.add_argument('--browser-path');p.add_argument('--webkit',action='store_true');p.add_argument('--widths',type=int,nargs='+',default=[320,390,430,744,820,1024,1440]);p.add_argument('--output',type=Path,default=Path('appearance-checks/review-fixes'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 server=serve(Path(__file__).resolve().parents[1]/'web/dist');results=[]
 try:
  async with async_playwright() as pw:
   browser=await pw.webkit.launch() if a.webkit else await pw.chromium.launch(executable_path=a.browser_path,chromium_sandbox=True)
   try:
    for width in a.widths:
     for design in ['classic','editorial']:
      for theme in ['light','dark']:
       c=await context_for(browser,width);await c.add_init_script(f"localStorage.setItem('xyz:design','{design}');localStorage.setItem('xyz:color-theme','{theme}')")
       task,_=fixtures();task.update(title='Me at the zoo',published_at='2005-04-24',created_at='2026-11-09T05:51:46Z',thumbnail='/data/thumbnails/cover.png',versions=[],markdown='# Me at the zoo\n\n## Contents\n\n- [AI Summary](#ai-summary)\n\n## AI Summary\n\nOriginal saved paragraph.\n\n| Design | Intent | Typography |\n| --- | --- | --- |\n| Classic | Familiar tool interface with readable notes | System sans-serif |')
       await c.route('**/api/video-notes/tasks/bench*',lambda r:r.fulfill(json=task))
       page=await c.new_page();await page.goto(f'http://127.0.0.1:{server.server_port}/');await page.get_by_role('group',name='Recent content type',exact=True).wait_for();await page.reload();await page.get_by_role('group',name='Recent content type',exact=True).wait_for()
       assert await page.locator('html').get_attribute('data-design')==design
       metrics=await page.evaluate('''() => {const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}};return {brand:box(document.querySelector('.publication-brand>span')),font:getComputedStyle(document.querySelector('.publication-brand>span')).fontSize,targets:[...document.querySelectorAll('.appearance-controls select,.appearance-controls button,.navigation-toggle')].map(box),filters:[...document.querySelectorAll('.dashboard-recent-filters button')].map(box),form:box(document.querySelector('#dashboard-add-content')),recent:box(document.querySelector('.dashboard-recent')),overflow:document.documentElement.scrollWidth>innerWidth+1}}''')
       assert not metrics['overflow'],(width,design,theme,metrics)
       if width<768:
        assert metrics['brand']['w']>0,(width,design,'hidden brand')
        # Two lines, not a clipped one-line wordmark or three squeezed lines.
        font=float(metrics['font'].replace('px',''));assert 2*font<=metrics['brand']['h']<3*font,(width,design,metrics['brand'])
        assert all(t['w']>=44 and t['h']>=44 for t in metrics['targets']),metrics
        assert all(t['right']<=width and t['x']>=0 for t in metrics['targets']),metrics
        assert max(f['y'] for f in metrics['filters'])-min(f['y'] for f in metrics['filters'])<1,(width,design,'wrapped filters',metrics)
       if design=='editorial' and width<=900:assert metrics['form']['y']>metrics['recent']['y'],'Intentional Editorial import order changed'
       if design=='classic' and width==1440:assert metrics['form']['h']<200,metrics
       if width in [390,1440]:await page.screenshot(path=str(a.output/f'{design}-{theme}-{width}-dashboard.png'))
       await page.goto(f'http://127.0.0.1:{server.server_port}/videos/bench');await page.locator('[data-rendering="formatted"]').wait_for();await page.get_by_text('Original saved paragraph.',exact=True).wait_for()
       assert await page.locator('.reader-body').get_by_role('heading',name='Contents',exact=True).count()==0
       assert await page.locator('.unified-outline').get_by_role('button',name='Contents',exact=True).count()==0
       assert await page.locator('.reader-metadata time').inner_text()=='Published 2005-04-24'
       assert await page.locator('.reader-metadata time').get_attribute('datetime')=='2005-04-24'
       assert await page.locator('.publication-reader-cover').count()==(1 if design=='editorial' else 0),'Approved cover removed'
       table=await page.locator('.markdown-table').evaluate('''e=>{const th=e.querySelector('th'),range=document.createRange();range.selectNodeContents(th);const r=range.getBoundingClientRect();return {headerHeight:r.height,font:parseFloat(getComputedStyle(th).fontSize),scroll:e.scrollWidth,client:e.clientWidth,pageOverflow:document.documentElement.scrollWidth>innerWidth+1}}''')
       assert table['headerHeight']<table['font']*2,(width,design,'split table label',table)
       assert not table['pageOverflow'],(width,design,table)
       if width==390:assert table['scroll']>table['client'],table
       if width in [390,1440]:await page.screenshot(path=str(a.output/f'{design}-{theme}-{width}-reader.png'))
       if design=='editorial':
        await page.goto(f'http://127.0.0.1:{server.server_port}/settings');await page.get_by_role('combobox',name='Transcription provider',exact=True).wait_for()
        assert 'sans-serif' in await page.get_by_role('combobox',name='Transcription provider',exact=True).evaluate('e=>getComputedStyle(e).fontFamily')
        assert 'Serif' in await page.locator('h1').evaluate('e=>getComputedStyle(e).fontFamily')
        if width==390 and theme=='light':await page.screenshot(path=str(a.output/'editorial-light-390-settings.png'))
       results.append({'width':width,'design':design,'theme':theme,'checks':'passed','dashboard':metrics,'table':table});print(json.dumps({'width':width,'design':design,'theme':theme,'checks':'passed'}),flush=True)
       await c.close()
   finally:await browser.close()
 finally:server.shutdown()
 (a.output/'results.json').write_text(json.dumps({'engine':'webkit' if a.webkit else 'chromium','data':'synthetic','results':results},indent=2))
if __name__=='__main__':asyncio.run(main())
