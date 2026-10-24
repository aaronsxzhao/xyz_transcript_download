// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import ProcessingPanel from '../src/components/ProcessingPanel'
import {TaskProgress} from '../src/components/TaskStatus'
import {useStore} from '../src/lib/store'
import {markSeen} from '../src/lib/seen'
const api=vi.hoisted(()=>({cancelJob:vi.fn(),cancelVideoTask:vi.fn(),deleteJob:vi.fn(),retryJob:vi.fn(),retryVideoTask:vi.fn(),fetchJob:vi.fn()}))
const toast=vi.hoisted(()=>vi.fn())
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:toast})}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();useStore.getState().reset();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();useStore.getState().reset()})
const job=(job_id:string,status:string,message='Working')=>({job_id,status,message,progress:status==='pending'?0:44,episode_id:'0123456789abcdef01234567',episode_title:job_id})
async function render(){await act(async()=>root.render(<MemoryRouter><ProcessingPanel/></MemoryRouter>))}
async function open(){await act(async()=>(node.querySelector('[aria-label="Open processing tasks"]') as HTMLButtonElement).click())}
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
 await act(async()=>root.render(<TaskProgress status="pending" progress={0}/>));expect(node.textContent).not.toContain('%');expect(node.querySelector('[role="progressbar"]')).toBeNull()
})
it('closing the last failed video does not reopen the drawer for the next queued task',async()=>{
 useStore.getState().setVideoTasks([{id:'video',title:'Failed video',status:'failed',progress:20,message:'Timeout',platform:'youtube'} as any]);await render();await open()
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
