"""Check rendered progress continuity, percent alignment and reduced motion."""
import asyncio, json, os, sys, time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.check_library_browser import serve
from scripts.check_page_loading import token
from scripts.check_appearance import choose
from playwright.async_api import async_playwright

async def main():
 server=serve(Path('web/dist').resolve())
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   for width in [390,820,1440]:
    for reduced in [False,True]:
     context=await browser.new_context(viewport={'width':width,'height':960},reduced_motion='reduce' if reduced else 'no-preference',service_workers='block')
     task=dict(id='motion',title='Progress motion review',status='transcribing',progress=22,updated_at='2026-10-31T15:00:00Z',platform='youtube')
     init={'type':'init','jobs':[],'video_tasks':[task]}
     await context.add_init_script("""localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_access_token',TOKEN);localStorage.setItem('xyz_user',JSON.stringify({id:'bench',authenticated:true}));window.WebSocket=class{static OPEN=1;readyState=1;constructor(){window.__socket=this;setTimeout(()=>this.onopen?.(),10)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify(INIT)}),10)}close(){}};""".replace('TOKEN',json.dumps(token(int(time.time())+3600))).replace('INIT',json.dumps(init)))
     page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     async def api(route):
      path=urlparse(route.request.url).path
      body={}
      if path=='/api/auth/config':body={'supabase_enabled':True}
      elif path=='/api/auth/me':body={'id':'bench','authenticated':True}
      elif path=='/api/jobs':body={'jobs':[]}
      elif path=='/api/content-updates':body={'items':[]}
      elif path=='/api/stats':body={}
      elif path.startswith('/api/video-notes/'):body={'tasks':[task],'channels':[]}
      elif path=='/api/summaries/recent':body=[]
      elif path.startswith('/api/library'):body={'items':[],'sources':[]}
      await route.fulfill(content_type='application/json',body=json.dumps(body))
     await page.route('**/api/**',api)
     await page.goto(f'http://127.0.0.1:{server.server_port}/')
     await choose(page,os.environ.get('SMOOTH_DESIGN','classic'),os.environ.get('SMOOTH_THEME','dark'))
     await page.get_by_role('button',name='Open processing tasks',exact=True).click()
     await page.locator('[role=dialog] [data-task-id=motion] .task-progress-fill').wait_for()
     samples=await page.evaluate("""async task=>{
      const row=document.querySelector('[role=dialog] [data-task-id=motion]');
      const samples=[];const start=performance.now();
      const send=(progress,status='transcribing')=>window.__socket.onmessage({data:JSON.stringify({type:'video_job_update',task:{...task,progress,status,updated_at:`2026-10-31T15:00:0${progress===70?1:2}Z`}})});
      send(70);setTimeout(()=>send(88),180);
      await new Promise(resolve=>{function frame(){const bar=row.querySelector('.task-progress-fill');const percent=row.querySelector('.task-progress-percent');samples.push({t:performance.now()-start,scale:new DOMMatrix(getComputedStyle(bar).transform).a,text:percent.textContent,width:percent.getBoundingClientRect().width});if(performance.now()-start<1400)requestAnimationFrame(frame);else resolve()}requestAnimationFrame(frame)});
      return samples;
     }""",task)
     scales=[s['scale'] for s in samples]
     assert all(b>=a-.0001 for a,b in zip(scales,scales[1:])),samples
     assert abs(scales[-1]-.88)<.001,samples[-1]
     assert max(s['width'] for s in samples)-min(s['width'] for s in samples)<.1
     if not reduced:assert any(.23<s<.69 for s in scales),scales
     else:assert all(any(abs(s-v)<.001 for v in [.22,.70,.88]) for s in scales),scales
     sheen=await page.locator('[role=dialog] .task-progress-fill').evaluate("e=>getComputedStyle(e,'::after').animationName")
     assert sheen == ('none' if reduced else 'task-sheen'),sheen
     await context.set_offline(True)
     await page.get_by_text("You're offline. Reconnect to refresh progress.").first.wait_for()
     paused=await page.locator('[role=dialog] .task-progress-fill').evaluate("e=>getComputedStyle(e,'::after').animationPlayState")
     if not reduced:assert paused=='paused',paused
     await context.set_offline(False)
     await page.wait_for_function("!document.querySelector('.task-progress[data-offline]')")
     assert not errors,errors
     assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
     await page.screenshot(path=f'/tmp/progress-motion-{os.environ.get("SMOOTH_DESIGN","classic")}-{width}-{reduced}.png')
     print(json.dumps({'width':width,'reduced_motion':reduced,'samples':len(samples),'final':samples[-1]['text'],'monotonic':True,'stable_percent_width':True}),flush=True)
     await context.close()
   await browser.close()
 finally:server.shutdown()

if __name__=='__main__':asyncio.run(main())
