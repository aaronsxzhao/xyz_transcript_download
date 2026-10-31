// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,useLocation} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import ProcessingPanel from '../src/components/ProcessingPanel'
import DashboardDialog from '../src/components/DashboardDialog'
import {TaskProgress} from '../src/components/TaskStatus'
import {useStore} from '../src/lib/store'
import {markSeen} from '../src/lib/seen'
const api=vi.hoisted(()=>({dismissVideoTask:vi.fn(),cancelJob:vi.fn(),cancelVideoTask:vi.fn(),deleteJob:vi.fn(),retryJob:vi.fn(),retryVideoTask:vi.fn(),fetchJob:vi.fn()}))
const toast=vi.hoisted(()=>vi.fn())
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:toast})}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();useStore.getState().reset();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();useStore.getState().reset()})
const job=(job_id:string,status:string,message='Working')=>({job_id,status,message,progress:status==='pending'?0:44,episode_id:'0123456789abcdef01234567',episode_title:job_id})
async function render(){await act(async()=>root.render(<MemoryRouter><ProcessingPanel/></MemoryRouter>))}
async function open(){await act(async()=>(node.querySelector('[aria-label="Open processing tasks"]') as HTMLButtonElement).click())}
it('lets historical Bilibili manifest failures retry instead of sending them to account settings',async()=>{
 const message='Could not read the complete Bilibili part list. Retry when source access is available; no first-part-only result was accepted.'
 useStore.getState().setVideoTasks([{id:'bili',...job('bili','failed',message),platform:'bilibili',url:'https://b23.tv/wY0ydIC',error:message}] as any)
 await render();await open()
 const row=document.querySelector('[data-task-id="bili"]')!
 expect(row.textContent).not.toContain('Source access required')
 expect(row.querySelector('a[href="/settings"]')).toBeNull()
 expect(row.querySelector('a[href="https://b23.tv/wY0ydIC"]')).not.toBeNull()
 const retry=[...row.querySelectorAll('button')].find(b=>b.textContent==='Retry')!
 expect(retry).toBeDefined()
 api.retryVideoTask.mockResolvedValue({task_id:'bili'})
 await act(async()=>retry.click())
 expect(api.retryVideoTask).toHaveBeenCalledWith('bili')
})
it.each(['podcast','video'] as const)('allows a cancelled %s to retry without exposing retry while stopping',async kind=>{
 if(kind==='podcast'){
  useStore.getState().setJobs([job('stopped','cancelled'),job('stopping','cancelling')]);
  api.retryJob.mockResolvedValue({new_job_id:'retry',message:'Retry started'});
  api.fetchJob.mockResolvedValue(job('retry','pending'));
 }else{
  useStore.getState().setVideoTasks([{id:'stopped',...job('stopped','cancelled')},{id:'stopping',...job('stopping','cancelling')}] as any);
  api.retryVideoTask.mockResolvedValue({task_id:'stopped'});
 }
 await render();await open();
 const row=document.querySelector('[data-task-id="stopped"]')!;
 const retry=[...row.querySelectorAll('button')].find(b=>b.textContent==='Retry');
 expect(retry).toBeDefined();
 expect(document.querySelector('[data-task-id="stopping"]')?.textContent).not.toContain('Retry');
 await act(async()=>retry!.click());
 expect(kind==='podcast'?api.retryJob:api.retryVideoTask).toHaveBeenCalledWith('stopped');
 expect((kind==='podcast'?useStore.getState().jobs.find(j=>j.job_id==='retry'):useStore.getState().videoTasks.find(t=>t.id==='stopped'))?.status).toBe('pending');
});
it('shows known podcast creation times without inventing dates for legacy jobs',async()=>{
 useStore.getState().setJobs([{...job('recent','failed'),created_at:1700000000},{...job('legacy','failed'),created_at:0}])
 await render();await open()
 expect(document.querySelector('[data-task-id="recent"] time')?.getAttribute('datetime')).toBe(new Date(1700000000*1000).toISOString())
 expect(document.querySelector('[data-task-id="legacy"] time')).toBeNull()
})
it('starts collapsed, separates running from queued, retains seen failures, and closes with Escape',async()=>{
 useStore.getState().setJobs([job('running','transcribing'),job('waiting','pending'),job('failed','failed')]);markSeen(['failed'])
 await render();expect(document.querySelector('[role="dialog"]')).toBeNull();expect(node.textContent).toContain('1 processing · 1 queued · 1 need attention')
 await open();const dialog=document.querySelector('[role="dialog"]')!
 expect(dialog.textContent).toContain('Needs attention · 1');expect(dialog.querySelector('[data-task-id="waiting"] [role="progressbar"]')).toBeNull();expect(dialog.querySelectorAll('[role="progressbar"]').length).toBe(1)
 await act(async()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})));expect(document.querySelector('[role="dialog"]')).toBeNull()
})
it('keeps a failed task after a failed dismiss and acknowledges it only after the server succeeds',async()=>{
 useStore.getState().setJobs([job('failed','failed')]);api.deleteJob.mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce({})
 await render();await open();const dismiss=()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Dismiss')!
 await act(async()=>dismiss().click());expect(document.querySelector('[data-task-id="failed"]')).not.toBeNull();expect(toast).toHaveBeenCalled()
 await act(async()=>dismiss().click());expect(useStore.getState().jobs).toEqual([])
})
it('explains source restrictions without a useless retry and never shows terminal percentages',async()=>{
 useStore.getState().setJobs([job('paid','failed','Purchase required to play the full episode')]);await render();await open()
 const dialog=document.querySelector('[role="dialog"]')!;expect(dialog.textContent).toContain('Source access required');expect(dialog.textContent).toContain('Open original episode');expect(dialog.textContent).not.toContain('Retry');expect(dialog.textContent).not.toContain('44%')
})
it('does not call an estimated progress value a measured percentage or show fake queued progress',async()=>{
 await act(async()=>root.render(<TaskProgress status="saving" progress={98}/>));expect(node.textContent).toContain('Saving and verifying');expect(node.textContent).toContain('~98%');expect(node.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('98')
 await act(async()=>root.render(<TaskProgress status="success" progress={100}/>));expect(node.textContent).toContain("100%");expect(node.textContent).not.toContain("~100%");expect(node.querySelector(".task-progress-fill")?.getAttribute("style")).toContain("scaleX(1)")
 await act(async()=>root.render(<TaskProgress status="pending" progress={0}/>));expect(node.textContent).not.toContain('%');expect(node.querySelector('[role="progressbar"]')).toBeNull()
})
it('closing the last failed video does not reopen the drawer for the next queued task',async()=>{
 useStore.getState().setVideoTasks([{id:'video',title:'Failed video',status:'failed',progress:20,message:'Timeout',platform:'youtube'} as any]);api.dismissVideoTask.mockResolvedValue({id:'video',status:'failed',task_dismissed:true});await render();await open()
 await act(async()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Dismiss')!.click())
 expect(document.querySelector('[role="dialog"]')).toBeNull()
 await act(async()=>useStore.getState().setJobs([job('new','pending')]))
 expect(node.querySelector('[aria-label="Open processing tasks"]')).not.toBeNull()
 expect(document.querySelector('[role="dialog"]')).toBeNull()
})
it('a late cancel acknowledgement preserves an already completed task',async()=>{
 useStore.getState().setVideoTasks([{id:'video',title:'Video',status:'downloading',progress:22,message:'Downloading',platform:'youtube'} as any]);api.cancelVideoTask.mockResolvedValue({status:'success'})
 await render();await open();await act(async()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Cancel')!.click())
 expect(useStore.getState().videoTasks[0].status).toBe('success')
 expect(useStore.getState().videoTasks[0].message).toBe('Completed')
})

it.each(['twitter','substack'])('keeps %s source access actions on the original platform',async platform=>{
 const url=platform==='twitter'?'https://x.com/writer/status/123':'https://writer.substack.com/p/post'
 useStore.getState().setVideoTasks([{id:'social',title:'Original source',platform,url,status:'failed',error:'LOGIN_REQUIRED',message:'Failed'} as any])
 await render();await open()
 const card=document.querySelector('[data-task-id="social"]')!
 expect(card.textContent).toContain('Open the original link')
 expect(card.querySelector(`a[href="${url}"]`)).not.toBeNull()
 expect(card.querySelector('a[href="/settings"]')).toBeNull()
})

it('identifies saved YouTube login failures separately from an active podcast and allows retry',async()=>{
 useStore.getState().setJobs([job('podcast-now','transcribing')])
 useStore.getState().setVideoTasks([{id:'old-video',title:'',url:'https://www.youtube.com/watch?v=abcdefghijk&private=never-display',platform:'youtube',status:'failed',progress:0,error:'LOGIN_REQUIRED',message:'Failed',created_at:'2026-04-13T09:23:31Z'} as any])
 await render();await open()
 const card=document.querySelector('[data-task-id="old-video"]')!
 expect(card.textContent).toContain('YouTube video · abcdefghijk')
 expect(card.textContent).toContain('Task created')
 expect(card.querySelector('time')?.getAttribute('datetime')).toBe('2026-04-13T09:23:31Z')
 expect(card.textContent).toContain('YouTube requested sign-in or anti-bot verification when this task ran.')
 expect(card.textContent).not.toContain('LOGIN_REQUIRED')
 expect(card.textContent).not.toContain('private=')
 expect(card.textContent).not.toContain('Processing content')
 expect(card.querySelector('a[href="https://www.youtube.com/watch?v=abcdefghijk"]')).not.toBeNull()
 expect(card.querySelector('a[href="/settings"]')?.textContent).toBe('Check YouTube account')
 api.retryVideoTask.mockResolvedValue({})
 await act(async()=>[...card.querySelectorAll('button')].find(b=>b.textContent==='Retry')!.click())
 expect(api.retryVideoTask).toHaveBeenCalledWith('old-video')
 expect(useStore.getState().videoTasks[0].status).toBe('pending')
 expect(useStore.getState().jobs[0].status).toBe('transcribing')
})

it('shows the real phase and count without inventing progress while waiting',async()=>{
 await act(async()=>root.render(<TaskProgress status="summarizing" progress={87} message="Checking coverage · 12/40 items checked"/>))
 const bar=node.querySelector('[role="progressbar"]')!
 expect(bar.getAttribute('aria-valuetext')).toContain('12/40 items checked')
 expect(node.textContent).toContain('Checking coverage')
 await act(async()=>root.render(<TaskProgress status="summarizing" progress={86} message="Verifying additions · 12/40 items checked"/>))
 expect(bar.getAttribute('aria-valuenow')).toBe('86') // Canonical shared state, not a component-local high watermark.
 expect(node.textContent).toContain('Verifying additions')
})

it('resets progress for a new attempt and never renders active 100 percent',async()=>{
 await act(async()=>root.render(<TaskProgress status="summarizing" progress={96} startedAt={100}/>))
 await act(async()=>root.render(<TaskProgress status="pending" progress={0} startedAt={200}/>))
 await act(async()=>root.render(<TaskProgress status="downloading" progress={10} startedAt={200}/>))
 expect(node.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('10')
 await act(async()=>root.render(<TaskProgress status="saving" progress={100} startedAt={200}/>))
 expect(node.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('99')
})


it.each(['/', '/viewer/0123456789abcdef01234567'])('reveals the requested summary after navigating from the task drawer at %s',async path=>{
 useStore.getState().setJobs([job('done','completed'),job('working','summarizing')])
 function Location(){const location=useLocation();return <p data-current-path>{location.pathname}</p>}
 await act(async()=>root.render(<MemoryRouter initialEntries={[path]}><Location/><ProcessingPanel/></MemoryRouter>))
 const opener=node.querySelector<HTMLButtonElement>('[aria-label="Open processing tasks"]')!
 opener.focus();await open()
 const link=document.querySelector<HTMLAnchorElement>('[role="dialog"] a[href^="/viewer/"]')!
 await act(async()=>link.click())
 expect(node.querySelector('[data-current-path]')?.textContent).toBe('/viewer/0123456789abcdef01234567')
 expect(document.querySelector('[role="dialog"]')).toBeNull()
 expect(document.activeElement).toBe(opener)
 expect(useStore.getState().jobs).toHaveLength(2)
})

it('hides the idle launcher but keeps an open drawer updated through completion',async()=>{
 useStore.getState().setJobs([job('done','completed')]);await render()
 expect(node.querySelector('.task-launcher')).toBeNull()
 await act(async()=>useStore.getState().setJobs([job('live','summarizing')]))
 await open()
 await act(async()=>useStore.getState().setJobs([job('live','completed')]))
 expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Finished')
 expect(node.querySelector('.task-launcher')).toBeNull()
})
it('refreshes the existing history entry and follows local upload progress through server handoff',async()=>{
 const refresh=vi.fn();window.addEventListener('xyz:processing-changed',refresh)
 const session={id:'upload',filename:'recording.mp4',phase:'uploading',percent:20,uploadedBytes:20,totalBytes:100,statusText:'Uploading',locationLabel:'Local file'} as any
 useStore.getState().upsertUploadSession(session)
 await act(async()=>root.render(<MemoryRouter><DashboardDialog kind="history" updates={[]} history={null} onClose={()=>{}}/></MemoryRouter>))
 expect(refresh).toHaveBeenCalledOnce()
 expect(node.textContent).toContain('20%');expect(node.textContent).not.toContain('No recent tasks')
 await act(async()=>useStore.getState().upsertUploadSession({...session,percent:70}))
 expect(node.textContent).toContain('70%');expect(node.textContent).toContain('reconnecting')
 await act(async()=>{useStore.getState().setWsConnected(true);useStore.getState().upsertUploadSession({...session,taskId:'server'});useStore.getState().setVideoTasks([{id:'server',status:'pending'} as any])})
 expect(node.textContent).not.toContain('recording.mp4');expect(node.textContent).not.toContain('reconnecting')
 window.removeEventListener('xyz:processing-changed',refresh)
})

it('explains quiet processing, clears the wait on new stage details, and distinguishes offline',async()=>{
 vi.useFakeTimers()
 const online=vi.spyOn(navigator,'onLine','get').mockReturnValue(true)
 try {
  await act(async()=>root.render(<TaskProgress status="transcribing" progress={44} compact/>))
  expect(node.textContent).not.toContain('No new progress')
  await act(async()=>vi.advanceTimersByTime(31000))
  expect(node.textContent).toContain('No new progress for 0m 30s')
  expect(node.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('44')
  await act(async()=>root.render(<TaskProgress status="transcribing" progress={44} message="Transcribing segment 2 of 8" compact/>))
  expect(node.textContent).not.toContain('No new progress')
  online.mockReturnValue(false)
  await act(async()=>window.dispatchEvent(new Event('offline')))
  expect(node.textContent).toContain("You're offline")
  expect(node.querySelector('.task-progress')?.hasAttribute('data-offline')).toBe(true)
  await act(async()=>root.render(<TaskProgress status="success" progress={100}/>))
  expect(node.textContent).not.toContain("You're offline")
  expect(node.querySelector('[role="progressbar"]')).toBeNull()
 } finally { online.mockRestore();vi.useRealTimers() }
})
