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
afterEach(() => {act(()=>root.unmount());node.remove();useStore.getState().reset();vi.useRealTimers();vi.unstubAllGlobals()})
async function mount() {await act(async()=>root.render(<MemoryRouter initialEntries={['/videos/one']}><Routes><Route path="/videos/:taskId" element={<VideoViewer/>}/></Routes></MemoryRouter>))}

it.each(['failed','cancelled','summarizing'])('keeps saved content and export actions available after status becomes %s',async status=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),status,error:status==='failed'?'Provider unavailable':''})
 await mount()
 expect(node.querySelector('.reader-body')?.textContent).toContain('Saved first note')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='Export')!.click())
 expect(node.textContent).toContain('Markdown')
 expect(node.textContent).toContain('PDF')
 expect(node.textContent).toContain('Send to Notion')
 if(status==='cancelled')expect(node.textContent).toContain('Processing was cancelled. Showing the saved note.')
})

it.each(['twitter','substack'])('explains %s source restrictions without a nonexistent account setup link',async platform=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),platform,status:'failed',error:'LOGIN_REQUIRED',message:'Failed',markdown:''})
 await mount()
 expect(node.textContent).toContain('Open the original link')
 expect(node.textContent).not.toContain('LOGIN_REQUIRED')
 expect(node.textContent).not.toContain('Check Settings')
})

it('retains settings access for a social processing provider failure',async()=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),platform:'substack',status:'failed',error:'Invalid model API key',message:'Failed',markdown:''})
 await mount()
 expect(node.textContent).toContain('Check Settings')
})

it('does not turn a local upload path into an external source link',async()=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),platform:'local',status:'failed',url:'/data/videos/upload.mp4',error:'Provider unavailable',markdown:''})
 await mount()
 expect(node.querySelector('a[href="/data/videos/upload.mp4"]')).toBeNull()
})

it('shows imported social text verbatim without a transcript tab or generated-note cleanup',async()=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),'platform':'substack',style:'original',formats:['original'],model:'',markdown:'# Original\n\n## Table of Contents\n- [Part](#part)\n\n## Part\n\n### 2.1 #### Literal source heading\n\nFinal original paragraph.'})
 await mount()
 expect([...node.querySelectorAll('[role=tab]')].map(el=>el.textContent?.trim())).toContain('Original text')
 expect([...node.querySelectorAll('[role=tab]')].map(el=>el.textContent?.trim())).not.toContain('Transcript')
 expect(node.querySelector('.reader-body')?.textContent).toContain('Table of Contents')
 expect(node.querySelector('.reader-body')?.textContent).toContain('2.1 #### Literal source heading')
 expect(node.querySelector('.reader-body')?.textContent).toContain('Final original paragraph.')
 expect(fetchVideoTranscript).not.toHaveBeenCalled()
})

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

it.each(['Failed','RATE_LIMITED'])('shows a readable source failure when the provider message is %s', async message => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),status:'failed',error:'RATE_LIMITED',message,markdown:''})
  await mount()
  expect(node.textContent).toContain('Too many requests')
  expect(node.textContent).not.toContain('RATE_LIMITED')
})

it('retains a descriptive server message for an unfamiliar classified failure', async () => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),status:'failed',error:'FFMPEG_MISSING',message:'FFmpeg is missing on the server.',markdown:''})
  await mount()
  expect(node.textContent).toContain('FFmpeg is missing on the server.')
  expect(node.textContent).not.toContain('FFMPEG_MISSING')
})

it('retains read recovery after a separate clipboard error is dismissed', async () => {
  await mount()
  vi.mocked(fetchVideoTask).mockRejectedValueOnce(new TypeError('Failed to fetch'))
  await act(async()=>useStore.getState().updateVideoTask(note('2026-10-24T00:00:04Z')))
  await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
  await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Dismiss')!.click())
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Failed to fetch')
  vi.mocked(fetchVideoTask).mockResolvedValue(note('2026-10-24T00:00:04Z','Current note'))
  await act(async()=>node.querySelector<HTMLButtonElement>('[role=alert] button')!.click())
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.textContent).toContain('Current note')
})

it('clears a previous copy failure after the user successfully copies again', async () => {
  await mount()
  await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Copy failed')
  vi.useFakeTimers()
  const writeText=vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator',{clipboard:{writeText}})
  await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
  expect(writeText).toHaveBeenCalled()
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.querySelector('[aria-label="Copied"]')).not.toBeNull()
})

it('clears a transcript read error when the user reopens the tab and it succeeds', async () => {
  await mount()
  vi.mocked(fetchVideoTranscript).mockRejectedValueOnce(new TypeError('Failed to fetch'))
  const tab=(name:string)=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()===name)!
  await act(async()=>tab('Transcript').click())
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Failed to fetch')
  await act(async()=>tab('Summary').click())
  await act(async()=>tab('Transcript').click())
  expect(node.textContent).toContain('Original words')
  expect(node.querySelector('[role=alert]')).toBeNull()
})
