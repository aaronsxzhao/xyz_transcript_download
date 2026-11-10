import json,time,traceback
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/deep-acceptance-private');out={'matrix':[]};url='http://127.0.0.1:18792/videos/audit-images'
def save():(R/'images-result.json').write_text(json.dumps(out,indent=2))
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,chromium_sandbox=True)
 try:
  for design in ['classic','editorial']:
   for theme in ['light','dark']:
    for w,h in [(1440,900),(768,1024),(390,844)]:
     c=b.new_context(viewport={'width':w,'height':h},ignore_https_errors=False);c.add_init_script(f"localStorage.setItem('xyz:design','{design}');localStorage.setItem('xyz:color-theme','{theme}')")
     p=c.new_page();p.set_default_timeout(20000);p.goto(url);article=p.locator('article[aria-label="Readable note"]');expect(article).to_be_visible();p.wait_for_load_state('networkidle');p.wait_for_timeout(300);expect(article.get_by_role('button',name='Enlarge Chart 1',exact=True)).to_be_visible()
     assert p.locator('html').get_attribute('data-design')==design;assert p.locator('html').get_attribute('data-theme')==theme
     for cycle in ['cold','reload']:
      if cycle=='reload':p.reload();expect(article).to_be_visible();p.wait_for_load_state('networkidle');p.wait_for_timeout(300)
      row={'design':design,'theme':theme,'width':w,'cycle':cycle,'images':[]};out['matrix'].append(row)
      for i in range(1,25):
       button=article.get_by_role('button',name=f'Enlarge Chart {i}',exact=True)
       if i!=24 or (R/'images-data/release-image').exists():button.scroll_into_view_if_needed()
       if i==24 and not (R/'images-data/release-image').exists():
        retry=article.get_by_role('button',name='Retry image');retry.scroll_into_view_if_needed();expect(retry).to_be_enabled();p.screenshot(path=str(R/'image-failure.png'));out['controlled_failure_visible']=True;(R/'images-data/release-image').touch();p.wait_for_timeout(3200);retry.click();button=article.get_by_role('button',name=f'Enlarge Chart {i}',exact=True)
       img=button.locator('img');expect(img).to_be_visible();p.wait_for_function('(im)=>im.complete && im.naturalWidth>0',arg=img.element_handle());img.evaluate('(im)=>im.decode()');d=img.evaluate('(im)=>{const r=im.getBoundingClientRect(),s=getComputedStyle(im);return {complete:im.complete,naturalWidth:im.naturalWidth,naturalHeight:im.naturalHeight,width:r.width,height:r.height,left:r.left,right:r.right,fit:s.objectFit}}')
       assert d['complete'] and d['naturalWidth']>0;assert d['left']>=-1 and d['right']<=w+1;assert d['fit']=='contain' or abs(d['width']/d['height']-d['naturalWidth']/d['naturalHeight'])<.03
       row['images'].append({'index':i,**d});save()
      assert not p.evaluate('document.documentElement.scrollWidth>innerWidth');row['pass']=True
      if cycle=='reload':p.screenshot(path=str(R/f'images-{design}-{theme}-{w}.png'))
     out['nav_comparison']={'outer_nav_in_reader':'OUTER_NAV_SENTINEL' in article.inner_text(),'inner_div_nav_in_reader':'INNER_NAV_SENTINEL' in article.inner_text()};c.close()
  out['status']='PASS';save()
 except Exception as e:out.update(status='FAIL',error_type=type(e).__name__,error_message=str(e)[:800],error_line=traceback.extract_tb(e.__traceback__)[-1].lineno);save()
 finally:b.close()
print(json.dumps({k:v for k,v in out.items() if k!='matrix'}))
