"""Synthetic long queue: bounded Classic panel, reachable controls, retained tasks."""
import json
import time
from pathlib import Path
from scripts.check_appearance import context_for, choose


async def check_processing_layout(browser, origin, width, output=None):
    for theme in ('light', 'dark'):
        context = await context_for(browser, width)
        now = time.time()
        jobs = [dict(job_id=f'layout-{i}', episode_id=f'layout-{i}',
                     episode_title=f'Synthetic long podcast task {i} · 多任务处理布局检查',
                     status='summarizing' if i < 2 else 'pending', progress=74 if i < 2 else 0,
                     started_at=now-300, revision=int(now*1e6),
                     message='Checking source accuracy · 6/11 source sections checked') for i in range(8)]
        await context.add_init_script('window.WebSocket=class {static OPEN=1;readyState=1;constructor(){setTimeout(()=>this.onopen?.(),1)}send(){setTimeout(()=>this.onmessage?.({data:JSON.stringify({type:"init",jobs:'+json.dumps(jobs)+',video_tasks:[]})}),1)}close(){}}')
        await context.route('**/api/jobs*', lambda r:r.fulfill(json={'jobs':jobs}))
        page=await context.new_page()
        await page.goto(origin+'/')
        await choose(page,'classic',theme)
        await page.reload()
        panel=page.get_by_role('complementary',name='Processing',exact=True)
        await panel.locator('.task-row').nth(7).wait_for(state='attached')
        await page.wait_for_function("document.documentElement.dataset.design==='classic'")
        box=await panel.bounding_box()
        if output:
            Path(output).mkdir(parents=True,exist_ok=True)
            await page.screenshot(path=str(Path(output)/f'classic-{theme}-{width}.png'),full_page=True)
        if width>1000:
            assert box['height']<=481,(width,theme,'queue stretches workspace',box)
            tasks=panel.locator('.dashboard-active-tasks')
            assert await tasks.evaluate('(e)=>e.scrollHeight>e.clientHeight'), 'long queue must scroll'
            await tasks.focus()
            await page.keyboard.press('End')
            await page.wait_for_function("(()=>{const e=document.querySelector('.dashboard-active-tasks');return e.scrollTop>0})()")
            last=panel.locator('.task-row').last
            await last.get_by_role('button',name='Cancel',exact=True).focus()
            assert await last.get_by_role('button',name='Cancel',exact=True).evaluate('(e)=>{const a=e.getBoundingClientRect(),b=e.closest(".dashboard-active-tasks").getBoundingClientRect();return a.top>=b.top&&a.bottom<=b.bottom+1}')
            history=panel.locator('.dashboard-history-link')
            assert await history.evaluate('(e)=>{const a=e.getBoundingClientRect(),b=e.closest("aside").getBoundingClientRect();return a.bottom<=b.bottom+1}')
        else:
            assert await panel.locator('.dashboard-active-tasks').evaluate('(e)=>getComputedStyle(e).overflowY!="auto"'), 'mobile order/layout unchanged'
        assert await panel.locator('.task-row').count()==8
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        print(json.dumps({'width':width,'theme':theme,'tasks':8,'panel_height':box['height'],'bounded_desktop':width>1000}),flush=True)
        await context.close()
