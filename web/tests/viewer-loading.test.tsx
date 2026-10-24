// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Viewer from '../src/pages/Viewer'
import { ApiError, fetchSummary, fetchTranscript } from '../src/lib/api'
vi.mock('../src/lib/api', async original => ({...await original<typeof import('../src/lib/api')>(),fetchSummary:vi.fn(),fetchTranscript:vi.fn()}))
vi.mock('../src/lib/cache',()=>({getCache:()=>null,setCache:vi.fn(),useWarmCache:()=>{},CacheKeys:{SUMMARY:(id:string)=>id}}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:vi.fn()}))
vi.mock('../src/lib/readingHistory',()=>({useRecordReading:()=>{}}))
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{},useDialog:()=>{}}))
vi.mock('../src/components/ReaderControls',()=>({default:()=>null}))
vi.mock('../src/components/SummaryText',()=>({default:({children}:any)=><>{children}</>}))
const summary={episode_id:'test',title:'Saved summary',overview:'Saved content',topics:[],key_points:[],takeaways:[]}
let cleanup:()=>void
beforeEach(()=>{vi.mocked(fetchSummary).mockReset();vi.mocked(fetchTranscript).mockReset();vi.stubGlobal('IntersectionObserver',class{observe(){} disconnect(){}})})
afterEach(()=>{cleanup?.();vi.unstubAllGlobals()})
async function mount(){const node=document.createElement('div');document.body.append(node);const root=createRoot(node);await act(async()=>root.render(<MemoryRouter initialEntries={['/viewer/test']}><Routes><Route path="/viewer/:eid" element={<Viewer/>}/></Routes></MemoryRouter>));cleanup=()=>{act(()=>root.unmount());node.remove()};return node}
it('keeps navigation and permits retrying a failed read without fetching the transcript',async()=>{
  let finish!:(value:any)=>void
  vi.mocked(fetchSummary).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  const node=await mount();expect(node.querySelector('[aria-label="Go back"]')).not.toBeNull();expect(node.textContent).toContain('connection was interrupted')
  await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Retry')!.click())
  await act(async()=>finish(summary));expect(node.textContent).toContain('Saved content');expect(fetchTranscript).not.toHaveBeenCalled()
})
it('stops automatic retries and resumes on a network online event',async()=>{
  vi.mocked(fetchSummary).mockRejectedValue(new TypeError('Failed to fetch'))
  const node=await mount();expect(fetchSummary).toHaveBeenCalledTimes(1);expect(node.textContent).toContain('connection was interrupted')
  vi.mocked(fetchSummary).mockResolvedValueOnce(summary)
  await act(async()=>window.dispatchEvent(new Event('online')))
  expect(node.textContent).toContain('Saved content');expect(node.querySelector('[role="alert"]')).toBeNull()
})
it('does not confuse a network failure with a missing summary',async()=>{
  vi.mocked(fetchSummary).mockRejectedValueOnce(new ApiError('Missing',404));vi.mocked(fetchTranscript).mockResolvedValueOnce({episode_id:'test',language:'en',duration:0,text:'Transcript',segments:[]})
  await mount();expect(fetchSummary).toHaveBeenCalledOnce();expect(fetchTranscript).toHaveBeenCalledOnce()
})
it('explains restricted incomplete content instead of rendering an ordinary summary',async()=>{
 vi.mocked(fetchSummary).mockResolvedValueOnce({...summary,key_points:[],topics:[],source_status:'purchase_required',source_message:'Purchase required on Xiaoyuzhou.',quality_warning:'This summary is based on an incomplete transcript.'})
 const node=await mount()
 expect(node.querySelector('[role="alert"]')?.textContent).toContain('Purchase required')
 expect(node.textContent).toContain('Previous incomplete result')
 expect(node.textContent).not.toContain('Key Points by Topic')
 expect(node.querySelector('[aria-label="Copy note"]')).toBeNull()
})

it('allows regeneration before the transcript tab has been loaded',async()=>{
 vi.mocked(fetchSummary).mockResolvedValueOnce(summary)
 const node=await mount()
 await act(async()=>{(node.querySelector('[aria-label="More summary actions"]') as HTMLButtonElement).click()})
 const regenerate=Array.from(node.querySelectorAll('button')).find(button=>button.textContent==='Regenerate summary')!
 expect(regenerate.disabled).toBe(false)
 expect(fetchTranscript).not.toHaveBeenCalled()
})
it('dismisses a copy failure without reloading the saved summary',async()=>{
 vi.mocked(fetchSummary).mockResolvedValue(summary)
 const node=await mount()
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
 const error=node.querySelector('[role=alert]')!
 expect(error.textContent).toContain('Copy failed')
 expect(error.querySelector('button')?.textContent).toBe('Dismiss')
 await act(async()=>error.querySelector<HTMLButtonElement>('button')!.click())
 expect(node.querySelector('[role=alert]')).toBeNull()
 expect(fetchSummary).toHaveBeenCalledOnce()
})
it('clears a copy error when the user successfully retries the copy action',async()=>{
 vi.mocked(fetchSummary).mockResolvedValue(summary)
 const node=await mount()
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Copy failed')
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:vi.fn().mockResolvedValue(undefined)}})
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Copy note"]')!.click())
 expect(node.querySelector('[role=alert]')).toBeNull()
 expect(fetchSummary).toHaveBeenCalledOnce()
 delete (navigator as any).clipboard
})

it('renders the complete chapter structure by default with opening conclusions and optional quotes',async()=>{
 const chapters={...summary,overview:'### 核心结论\n- Keep conditions.\n\n### 节目概览\nA full overview.',topics:['模型','风险'],key_points:[
  {topic:'模型',summary:'#### 基准\n\n1 个百分点，全球不含中国。',original_quote:'First original quote',timestamp:'28:29'},
  {topic:'模型',summary:'#### 情景\n\nConditional on B50.',original_quote:'Second original quote',timestamp:''},
  {topic:'风险',summary:'#### 不及预期\n\nTrack actual production.',original_quote:'',timestamp:''},
 ]}
 vi.mocked(fetchSummary).mockResolvedValueOnce(chapters)
 const node=await mount()
 expect(node.querySelectorAll('[data-topic-card]').length).toBe(2)
 expect([...node.querySelectorAll('.topic-toggle')].every(el=>el.getAttribute('aria-expanded')==='true')).toBe(true)
 expect(node.textContent).toContain('1 个百分点，全球不含中国。')
 expect(node.textContent).toContain('Conditional on B50.')
 expect(node.querySelector('#summary-conclusions')?.textContent).toContain('Keep conditions.')
 expect(node.querySelector('#summary-overview')?.parentElement?.textContent).toContain('A full overview.')
 expect(node.querySelector('details.reader-quote')?.hasAttribute('open')).toBe(false)
 expect(node.querySelector('details.reader-quote summary')?.textContent).toContain('28:29')
 expect(fetchTranscript).not.toHaveBeenCalled()
 await act(async()=>{(node.querySelector('.topic-toggle') as HTMLButtonElement).click()})
 expect(node.querySelectorAll('.topic-content').length).toBe(1)
 const expand=[...node.querySelectorAll('button')].find(el=>el.textContent==='Expand all')!
 await act(async()=>expand.click())
 expect(node.querySelectorAll('.topic-content').length).toBe(2)
})
