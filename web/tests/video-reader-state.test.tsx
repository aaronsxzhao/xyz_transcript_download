// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter, Routes, Route} from 'react-router-dom'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import VideoViewer from '../src/pages/VideoViewer'
import {fetchVideoTask, fetchVideoTranscript, type VideoTask} from '../src/lib/api'
import {useStore} from '../src/lib/store'

vi.mock('../src/lib/api', async load => ({...await load<object>(), fetchVideoTask:vi.fn(), fetchVideoTranscript:vi.fn()}))
vi.mock('../src/lib/cache', () => ({getCache:()=>null, setCache:vi.fn(), removeCache:vi.fn(), useWarmCache:()=>{}, CacheKeys:{VIDEO_NOTE:(id:string)=>id}}))
vi.mock('../src/lib/pageTiming', () => ({usePageTiming:()=>{}}))
vi.mock('../src/lib/readingHistory', () => ({useRecordReading:()=>{}}))
vi.mock('../src/lib/reading', () => ({useReadingPosition:()=>{}, useDialog:()=>{}}))
vi.mock('../src/lib/safeHtml', () => ({markdownToSafeHtml:vi.fn().mockResolvedValue('<p>Note</p>')}))
vi.mock('../src/components/DeferredView', () => ({deferView:()=>({fallback}:any)=><>{fallback}</>}))
const note = (updated_at='2026-10-24T00:00:01Z', markdown='Saved first note'):VideoTask => ({
  id:'one', title:'Trading lesson', platform:'youtube', channel:'Course', status:'success', progress:100,
  message:'Complete', error:'', markdown, updated_at, created_at:'2026-10-24', url:'https://youtu.be/abcdefghijk', duration:120,
  style:'detailed', formats:['summary'], thumbnail:'', model:'test',
} as VideoTask)
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(() => {
  vi.clearAllMocks(); useStore.getState().reset(); localStorage.clear(); sessionStorage.clear()
  vi.stubGlobal('IntersectionObserver',class {observe(){} disconnect(){}})
  vi.mocked(fetchVideoTask).mockResolvedValue(note())
  vi.mocked(fetchVideoTranscript).mockResolvedValue({transcript:{text:'Original words',duration:120,segments:[]}} as any)
  node=document.createElement('div'); document.body.append(node); root=createRoot(node)
})
afterEach(() => {act(()=>root.unmount());node.remove();useStore.getState().reset();vi.unstubAllGlobals()})
async function mount() {await act(async()=>root.render(<MemoryRouter initialEntries={['/videos/one']}><Routes><Route path="/videos/:taskId" element={<VideoViewer/>}/></Routes></MemoryRouter>))}

it('reloads a completed note after a regeneration in another page, even when the final status is unchanged', async () => {
  await mount()
  expect(node.textContent).toContain('Saved first note')
  await act(async()=>useStore.getState().updateVideoTask({...note(),status:'summarizing',progress:70,updated_at:'2026-10-24T00:00:02Z'}))
  vi.mocked(fetchVideoTask).mockResolvedValue(note('2026-10-24T00:00:03Z','New complete note'))
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:03Z')))
  expect(fetchVideoTask).toHaveBeenCalledTimes(2)
  expect(node.textContent).toContain('New complete note')
})

it('reconciles a newer completed revision once without rereading an older event', async () => {
  await mount()
  vi.mocked(fetchVideoTask).mockResolvedValue(note('2026-10-24T00:00:04Z','Recovered screenshots and revised note'))
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:04Z')))
  expect(node.textContent).toContain('Recovered screenshots and revised note')
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:02Z')))
  expect(fetchVideoTask).toHaveBeenCalledTimes(2)
})

it('does not read a transcript from an unverified processing revision', async () => {
  await mount()
  await act(async()=>useStore.getState().updateVideoTask({...note(),status:'transcribing',progress:45,updated_at:'2026-10-24T00:00:02Z'}))
  await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='Transcript')!.click())
  expect(fetchVideoTranscript).not.toHaveBeenCalled()
  expect(node.textContent).toContain('Waiting for the latest transcript')
  let finish!:(task:VideoTask)=>void
  vi.mocked(fetchVideoTask).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:03Z')))
  expect(fetchVideoTranscript).not.toHaveBeenCalled()
  await act(async()=>finish(note('2026-10-24T00:00:03Z')))
  expect(fetchVideoTranscript).toHaveBeenCalledTimes(1)
  expect(node.textContent).toContain('Original words')
})

it('recovers a failed initial note read on an online event', async () => {
  vi.mocked(fetchVideoTask).mockRejectedValueOnce(new TypeError('Failed to fetch'))
  await mount()
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Failed to fetch')
  await act(async()=>window.dispatchEvent(new Event('online')))
  expect(node.textContent).toContain('Saved first note')
})

it('explains a clipboard failure without offering a retry that just reloads the note', async () => {
  await mount()
  await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
  const error=node.querySelector('[role=alert]')!
  expect(error.textContent).toContain('Copy failed')
  expect(error.querySelector('button')?.textContent).toBe('Dismiss')
  await act(async()=>error.querySelector('button')!.click())
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(fetchVideoTask).toHaveBeenCalledTimes(1)
})

it('does not clear an action error when an unrelated metadata refresh finishes', async () => {
  await mount()
  let finish!:(task:VideoTask)=>void
  vi.mocked(fetchVideoTask).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:04Z')))
  await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
  await act(async()=>finish(note('2026-10-24T00:00:04Z')))
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Copy failed')
  expect(node.querySelector('[role=alert] button')?.textContent).toBe('Dismiss')
})

it('shows a readable source failure instead of a raw status code', async () => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),status:'failed',error:'RATE_LIMITED',message:'Failed',markdown:''})
  await mount()
  expect(node.textContent).toContain('Too many requests')
  expect(node.textContent).not.toContain('RATE_LIMITED')
})
