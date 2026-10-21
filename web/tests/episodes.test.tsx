// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Episodes from '../src/pages/Episodes'
import { ApiError, fetchEpisodes, fetchPodcast } from '../src/lib/api'

vi.mock('../src/lib/api', async importOriginal => ({...await importOriginal<typeof import('../src/lib/api')>(), fetchEpisodes:vi.fn(), fetchPodcast:vi.fn()}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:vi.fn()})}))
vi.mock('../src/lib/cache',()=>({getCache:()=>null,setCache:vi.fn(),useWarmCache:()=>{},CacheKeys:{PODCAST:(id:string)=>id,EPISODES:(id:string)=>id,PODCASTS:'podcasts'}}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:vi.fn()}))
vi.mock('../src/lib/seen',()=>({markSeen:vi.fn(),isNewItem:()=>false}))
vi.mock('../src/lib/summaryPrefetch',()=>({prefetchSummary:vi.fn()}))
const row=(n=0)=>({eid:`ep-${n}`,pid:'test',title:`Episode ${n}`,pub_date:'',duration:10,status:'pending',has_summary:false,has_transcript:false})
let cleanup:()=>void
beforeEach(()=>{
  vi.mocked(fetchEpisodes).mockReset(); vi.mocked(fetchPodcast).mockReset()
  vi.mocked(fetchPodcast).mockImplementation(()=>new Promise(()=>{}))
})
afterEach(()=>{cleanup?.();vi.useRealTimers()})
async function mount() {
  const node=document.createElement('div');document.body.append(node)
  const root=createRoot(node)
  await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts/test/episodes']}><Routes><Route path="/podcasts/:pid/episodes" element={<Episodes/>}/></Routes></MemoryRouter>))
  cleanup=()=>{act(()=>root.unmount());node.remove()}
  return node
}
it('keeps navigation visible while loading and recovers one transient read failure without waiting for metadata',async()=>{
  let finish!:(data:any)=>void
  vi.mocked(fetchEpisodes).mockRejectedValueOnce(new TypeError('Failed to fetch')).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  const node=await mount()
  expect(node.querySelector('[aria-label="Go back"]')).not.toBeNull()
  expect(node.textContent).toContain('Retrying once')
  await act(async()=>finish([row()]))
  expect(node.textContent).toContain('Episode 0')
  expect(node.querySelector('[role="status"]')).toBeNull()
  expect(fetchEpisodes).toHaveBeenCalledTimes(2)
})
it('shows missing-podcast errors immediately without retrying or waiting for metadata',async()=>{
  vi.mocked(fetchEpisodes).mockRejectedValueOnce(new ApiError('Missing',404))
  const node=await mount()
  expect(node.querySelector('[role="alert"]')?.textContent).toContain('no longer available')
  expect(fetchEpisodes).toHaveBeenCalledOnce()
})
it('stops after one automatic retry and allows a manual retry of the first page',async()=>{
  vi.mocked(fetchEpisodes).mockRejectedValue(new Error('Loading timed out. Please retry.'))
  const node=await mount()
  expect(fetchEpisodes).toHaveBeenCalledTimes(2)
  expect(node.querySelector('[role="alert"]')?.textContent).toContain('timed out')
  vi.mocked(fetchEpisodes).mockResolvedValueOnce([row()] as any)
  await act(async()=>node.querySelector<HTMLButtonElement>('[role="alert"] button')!.click())
  expect(node.textContent).toContain('Episode 0')
  expect(node.querySelector('[role="alert"]')).toBeNull()
})
it('retains the first page and retries the correct offset when loading more fails with metadata unavailable',async()=>{
  vi.mocked(fetchEpisodes).mockResolvedValueOnce(Array.from({length:50},(_,n)=>row(n)) as any).mockRejectedValueOnce(new TypeError('Network'))
  const node=await mount()
  const more=Array.from(node.querySelectorAll('button')).find(b=>b.textContent==='Load more episodes')!
  await act(async()=>more.click())
  expect(node.textContent).toContain('Episode 49')
  vi.mocked(fetchEpisodes).mockResolvedValueOnce([row(50)] as any)
  await act(async()=>node.querySelector<HTMLButtonElement>('[role="alert"] button')!.click())
  expect(fetchEpisodes).toHaveBeenLastCalledWith('test',50)
  expect(node.textContent).toContain('Episode 50')
})
