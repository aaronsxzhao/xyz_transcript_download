import json,re,sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
R=Path('/workspace/deep-acceptance-private');out={}
with sync_playwright() as w:
 b=w.chromium.launch(executable_path='/usr/bin/chromium',chromium_sandbox=True);p=b.new_page(viewport={'width':1440,'height':900})
 p.goto('http://127.0.0.1:18791/');p.get_by_role('button',name=re.compile('Task history|Review tasks')).first.click();dialog=p.get_by_role('dialog',name='Task history');expect(dialog).to_be_visible();out['failure_in_history']='fail' in dialog.inner_text().lower();p.screenshot(path=str(R/'recovery-tasks.png'))
 p.goto('http://127.0.0.1:18791/viewer/a');panel=p.locator('#podcast-summary');expect(panel).to_be_visible();expect(panel).to_contain_text('Saved synthetic result');p.get_by_role('tab',name='Transcript',exact=True).click();expect(p.get_by_text('Synthetic transcript',exact=True)).to_be_visible();p.reload();p.get_by_role('tab',name='Summary',exact=True).click();expect(panel).to_contain_text('Saved synthetic result');out['reader_transcript_reload']=True;p.screenshot(path=str(R/'recovery-reader.png'))
 p.goto('http://127.0.0.1:18793/source.html');text=p.locator('body').inner_text();out['source_nav']={'outer':'OUTER_NAV_SENTINEL' in text,'inner':'INNER_NAV_SENTINEL' in text};p.screenshot(path=str(R/'source-navigation.png'))
 db=sqlite3.connect(R/'images-data/xyz.db');saved=db.execute("select markdown from video_tasks where id='audit-images'").fetchone()[0].replace('\\_','_');out['saved_nav']={'outer':'OUTER_NAV_SENTINEL' in saved,'inner':'INNER_NAV_SENTINEL' in saved};db.close()
 p.goto('http://127.0.0.1:18792/videos/audit-images');article=p.locator('article[aria-label="Readable note"]');expect(article).to_be_visible();p.wait_for_load_state('networkidle');text=article.inner_text();out['reader_nav']={'outer':'OUTER_NAV_SENTINEL' in text,'inner':'INNER_NAV_SENTINEL' in text};p.screenshot(path=str(R/'saved-navigation.png'));out['status']='PASS';b.close()
(R/'recovery-ui-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
