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
