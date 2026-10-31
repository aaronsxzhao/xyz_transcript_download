// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter, Routes, Route} from 'react-router-dom'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import VideoViewer from '../src/pages/VideoViewer'
import {downloadMarkdown} from '../src/lib/markdownDownload'
vi.mock('../src/lib/markdownDownload',()=>({downloadMarkdown:vi.fn()}))
import {fetchVideoTask, fetchVideoTranscript, fetchVideoVersion, retryVideoTask, type VideoTask} from '../src/lib/api'
import {useStore} from '../src/lib/store'
import {retryCoverageReview} from '../src/lib/coverageReview'
vi.mock('../src/lib/coverageReview',()=>({retryCoverageReview:vi.fn()}))

vi.mock('../src/lib/api', async load => ({...await load<object>(), fetchVideoTask:vi.fn(), fetchVideoTranscript:vi.fn(), fetchVideoVersion:vi.fn(), retryVideoTask:vi.fn()}))
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
  document.documentElement.dataset.design='classic'
  vi.stubGlobal('IntersectionObserver',class {observe(){} disconnect(){}})
  vi.mocked(fetchVideoTask).mockResolvedValue(note())
  vi.mocked(fetchVideoTranscript).mockResolvedValue({transcript:{text:'Original words',duration:120,segments:[]}} as any)
  node=document.createElement('div'); document.body.append(node); root=createRoot(node)
})
afterEach(() => {act(()=>root.unmount());node.remove();useStore.getState().reset();vi.useRealTimers();vi.unstubAllGlobals()})
async function mount() {await act(async()=>root.render(<MemoryRouter initialEntries={['/videos/one']}><Routes><Route path="/videos/:taskId" element={<VideoViewer/>}/></Routes></MemoryRouter>))}

it('retries unfinished coverage once, keeps the note readable and shows progress',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(fetchVideoTask).mockResolvedValue(note(undefined,'> ℹ️ Notes were generated, but the full-source coverage review did not complete. Completeness is unverified; compare with Transcript.\n\nSaved argument.'))
 vi.mocked(retryCoverageReview).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 await mount()
 const button=[...node.querySelectorAll('button')].find(b=>b.textContent==='Retry coverage review')!
 await act(async()=>{button.click();button.click()})
 expect(retryCoverageReview).toHaveBeenCalledOnce()
 expect(retryVideoTask).not.toHaveBeenCalled()
 expect(button.disabled).toBe(true)
 expect(button.textContent).toBe('Submitting…')
 await act(async()=>finish({task_id:'one'}))
 expect(node.textContent).toContain('Checking coverage. Showing the saved note.')
 expect(node.querySelector('.reader-body')?.textContent).toContain('Saved argument.')
 await act(async()=>useStore.getState().updateVideoTask({...note('2026-10-31T12:00:00Z'),status:'summarizing',progress:42,message:'Coverage review · 4/9 source sections reviewed'}))
 expect(node.querySelector('[role="progressbar"]')).not.toBeNull()
 expect(button.textContent).toBe('Review in progress…')
})

it('keeps an unsuccessful coverage retry actionable and shows the server explanation',async()=>{
 vi.mocked(fetchVideoTask).mockResolvedValue(note(undefined,'> ℹ️ 摘要已生成，但全文覆盖核对未完成；完整性尚未验证，可对照 Transcript 阅读。\n\nSaved argument.'))
 vi.mocked(retryCoverageReview).mockRejectedValue(new Error('Queue unavailable. Retry review.'))
 await mount()
 const button=[...node.querySelectorAll('button')].find(b=>b.textContent==='Retry coverage review')!
 await act(async()=>button.click())
 expect(node.textContent).toContain('Queue unavailable. Retry review.')
 expect(button.disabled).toBe(false)
 expect(node.querySelector('.reader-body')?.textContent).toContain('Saved argument.')
})

it.each(['web','substack','twitter'])('does not add a second cover above the original %s article',async platform=>{
 document.documentElement.dataset.design='editorial'
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),platform,style:'original',thumbnail:'https://images.example/cover.jpg',markdown:'![Original cover](https://images.example/cover.jpg)\n\nOriginal article text.'})
 await mount()
 expect(node.querySelector('.publication-reader-cover')).toBeNull()
 expect(node.querySelectorAll('.reader-body img')).toHaveLength(1)
 expect(node.querySelector('.reader-body img')?.getAttribute('src')).toBe('https://images.example/cover.jpg')
 expect(node.querySelector('.reader-body')?.textContent).toContain('Original article text.')
})

it('retains the editorial cover for generated video summaries',async()=>{
 document.documentElement.dataset.design='editorial'
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),thumbnail:'https://images.example/video.jpg'})
 await mount()
 expect(node.querySelector('.publication-reader-cover img')?.getAttribute('src')).toBe('/api/image-proxy?url=https%3A%2F%2Fimages.example%2Fvideo.jpg&v=2')
})

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

it.each([
 ['article','original','Original article',false],
 ['audio','detailed','Audio summary',true],
])('labels generic %s content accurately',async(type,style,label,showDuration)=>{
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),platform:'web',style,source_metadata:{type:type as 'article'|'audio'},model:style==='original'?'':'test'})
 await mount()
 expect(node.querySelector('.reader-breadcrumb')?.textContent||node.textContent).toContain(label)
 const header=node.querySelector('.unified-header')!
 expect(header.textContent?.includes('2:00')).toBe(showDuration)
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

it('shows an original article title once while retaining the exact Markdown for export',async()=>{
 const markdown='# Trading lesson\n\nAuthor: Writer\n\nPublished: 2026-09-30T15:27:42+00:00\n\n## A different section\n\nComplete original paragraph.'
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(undefined,markdown),style:'original',platform:'substack',channel:'Writer',published_at:'2026-09-30T15:27:42Z'})
 await mount()
 expect(node.querySelector('h1')?.textContent).toBe('Trading lesson')
 expect(node.querySelector('.reader-body h1')).toBeNull()
 expect(node.querySelector('.reader-body')?.textContent).not.toContain('Author: Writer')
 expect(node.querySelector('.reader-body')?.textContent).not.toContain('Published: 2026')
 expect(node.querySelector('.reader-body h2')?.textContent).toBe('A different section')
 expect(node.querySelector('.reader-body')?.textContent).toContain('Complete original paragraph.')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='Export')!.click())
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='Markdown')!.click())
 await act(async()=>vi.dynamicImportSettled())
 expect(downloadMarkdown).toHaveBeenCalledWith(markdown,'Trading lesson')
})

it('offers an explicit start action for discovered content instead of a processing spinner',async()=>{
 let accepted!:(value:any)=>void
 vi.mocked(fetchVideoTask).mockResolvedValue({...note(),status:'discovered',progress:0,markdown:'',message:''})
 vi.mocked(retryVideoTask).mockImplementationOnce(()=>new Promise(resolve=>{accepted=resolve}))
 await mount()
 const section=node.querySelector('[aria-label="Unprocessed content"]')!
 expect(section.textContent).toContain('Not processed yet')
 expect(section.querySelector('progress')).toBeNull()
 const start=[...section.querySelectorAll('button')].find(b=>b.textContent==='Start processing')!
 await act(async()=>{start.click();start.click()})
 expect(retryVideoTask).toHaveBeenCalledOnce()
 expect(start.disabled).toBe(true)
 await act(async()=>accepted({task_id:'one'}))
 expect(node.querySelector('[aria-label="Unprocessed content"]')).toBeNull()
 expect(useStore.getState().videoTasks.find(t=>t.id==='one')?.status).toBe('pending')
})


it('opens the latest saved version when the current note is empty', async () => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),markdown:'',versions:[{id:'saved',task_id:'one',style:'detailed',model_name:'test',created_at:'2026-10-31'}]})
  vi.mocked(fetchVideoVersion).mockResolvedValue({id:'saved',task_id:'one',content:'Recovered saved summary',style:'detailed',model_name:'test',created_at:'2026-10-31'})
  await mount()
  expect(fetchVideoVersion).toHaveBeenCalledWith('one','saved',expect.any(AbortSignal))
  expect(node.textContent).toContain('Recovered saved summary')
})

it('shows recovery controls instead of a blank successful summary', async () => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),markdown:'',versions:[]})
  await mount()
  expect(node.textContent).toContain('No summary content.')
  expect(node.querySelector('[role=alert] button')).not.toBeNull()
})

it('reports an empty saved version instead of silently rendering a blank reader', async () => {
  vi.mocked(fetchVideoTask).mockResolvedValue({...note(),markdown:'',versions:[{id:'empty',task_id:'one',style:'detailed',model_name:'test',created_at:'2026-10-31'}]})
  vi.mocked(fetchVideoVersion).mockResolvedValue({id:'empty',task_id:'one',content:'',style:'detailed',model_name:'test',created_at:'2026-10-31'})
  await mount()
  expect(node.textContent).toContain('Saved version is empty.')
  expect(node.querySelector('[role=alert] button')).not.toBeNull()
})
