// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Dashboard from '../src/pages/Dashboard'
import {clearCache} from '../src/lib/cache'
const api=vi.hoisted(()=>({processEpisode:vi.fn(),generateVideoNote:vi.fn()}))
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api,
 fetchStats:async()=>({podcasts:0,episodes:0,transcripts:0,summaries:0}),fetchRecentSummaries:async()=>[],fetchRecentVideoTasks:async()=>({tasks:[]}),fetchContentUpdates:async()=>({items:[]})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
const toast=vi.hoisted(()=>vi.fn())
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:toast})}))
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{vi.resetAllMocks();clearCache();localStorage.clear();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache()})
it('submits Spotify episodes through the advertised podcast entry',async()=>{
 api.processEpisode.mockResolvedValue({job_id:'spotify-job'})
 await act(async()=>root.render(<MemoryRouter><Dashboard/></MemoryRouter>))
 const input=node.querySelector<HTMLInputElement>('[aria-label="Podcast episode or video URL"]')!
 const url='https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ?si=share'
 await act(async()=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,url)
  input.dispatchEvent(new Event('input',{bubbles:true}))
 })
 expect(node.textContent).toContain('Xiaoyuzhou · Spotify · YouTube')
 await act(async()=>input.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))
 expect(api.processEpisode).toHaveBeenCalledWith(url)
 expect(api.generateVideoNote).not.toHaveBeenCalled()
 expect(input.value).toBe('')
})
