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
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{},useDialog:()=>{}}))
vi.mock('../src/components/ReaderControls',()=>({default:()=>null}))
vi.mock('../src/components/SummaryText',()=>({default:({children}:any)=><>{children}</>}))
const summary={episode_id:'test',title:'Saved summary',overview:'Saved content',topics:[],key_points:[],takeaways:[]}
let cleanup:()=>void
beforeEach(()=>{vi.mocked(fetchSummary).mockReset();vi.mocked(fetchTranscript).mockReset();vi.stubGlobal('IntersectionObserver',class{observe(){} disconnect(){}})})
afterEach(()=>{cleanup?.();vi.unstubAllGlobals()})
async function mount(){const node=document.createElement('div');document.body.append(node);const root=createRoot(node);await act(async()=>root.render(<MemoryRouter initialEntries={['/viewer/test']}><Routes><Route path="/viewer/:eid" element={<Viewer/>}/></Routes></MemoryRouter>));cleanup=()=>{act(()=>root.unmount());node.remove()};return node}
it('recovers Failed to fetch without dropping navigation or fetching the transcript',async()=>{
  let finish!:(value:any)=>void
  vi.mocked(fetchSummary).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  const node=await mount();expect(node.querySelector('[aria-label="Go back"]')).not.toBeNull();expect(node.textContent).toContain('Retrying once')
  await act(async()=>finish(summary));expect(node.textContent).toContain('Saved content');expect(fetchTranscript).not.toHaveBeenCalled()
})
it('stops automatic retries and resumes on a network online event',async()=>{
  vi.mocked(fetchSummary).mockRejectedValue(new TypeError('Failed to fetch'))
  const node=await mount();expect(fetchSummary).toHaveBeenCalledTimes(2);expect(node.textContent).toContain('connection was interrupted')
  vi.mocked(fetchSummary).mockResolvedValueOnce(summary)
  await act(async()=>window.dispatchEvent(new Event('online')))
  expect(node.textContent).toContain('Saved content');expect(node.querySelector('[role="alert"]')).toBeNull()
})
it('does not confuse a network failure with a missing summary',async()=>{
  vi.mocked(fetchSummary).mockRejectedValueOnce(new ApiError('Missing',404));vi.mocked(fetchTranscript).mockResolvedValueOnce({episode_id:'test',language:'en',duration:0,text:'Transcript',segments:[]})
  await mount();expect(fetchSummary).toHaveBeenCalledOnce();expect(fetchTranscript).toHaveBeenCalledOnce()
})
