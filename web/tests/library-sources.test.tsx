// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Library from '../src/pages/Library'
import {clearCache} from '../src/lib/cache'

const api=vi.hoisted(()=>({fetchLibrary:vi.fn(),fetchLibrarySources:vi.fn()}))
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{}}))
vi.mock('../src/lib/readingHistory',()=>({useReadingHistory:()=>[]}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.resetAllMocks();localStorage.clear();clearCache()
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
 api.fetchLibrary.mockResolvedValue({items:[{id:'one',kind:'podcast',title:'Visible note',source:'Recent show',status:'completed',date:'2026-10-25'}],next_cursor:'older-page'})
})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache()})
const render=()=>act(async()=>root.render(<MemoryRouter><Library/></MemoryRouter>))
const options=()=>[...node.querySelectorAll('select[aria-label="Podcast or channel"] option')].map(o=>o.textContent)

it('offers sources from later pages and keeps them while filtering notes',async()=>{
 api.fetchLibrarySources.mockResolvedValueOnce({sources:['Recent show'],next_cursor:'Recent show'})
  .mockResolvedValueOnce({sources:['Older show'],next_cursor:null})
 await render()
 await vi.waitFor(()=>expect(options()).toContain('Older show'))
 expect(api.fetchLibrarySources.mock.calls.map(c=>c[0])).toEqual(['','Recent show'])
 const select=node.querySelector('select[aria-label="Podcast or channel"]') as HTMLSelectElement
 await act(async()=>{select.value='Older show';select.dispatchEvent(new Event('change',{bubbles:true}))})
 await vi.waitFor(()=>expect(api.fetchLibrary).toHaveBeenLastCalledWith(expect.stringContaining('source=Older+show'),'',expect.any(AbortSignal)))
 expect(options()).toEqual(['All sources','Older show','Recent show'])
 expect(api.fetchLibrarySources).toHaveBeenCalledTimes(2)
})

it('allows retrying a partial catalog without hiding readable notes',async()=>{
 api.fetchLibrarySources.mockResolvedValueOnce({sources:['Recent show'],next_cursor:'Recent show'})
  .mockRejectedValueOnce(new Error('Connection interrupted'))
 await render()
 await vi.waitFor(()=>expect(node.textContent).toContain('Retry sources'))
 expect(node.textContent).toContain('Visible note')
 api.fetchLibrarySources.mockResolvedValueOnce({sources:['Recent show','Older show'],next_cursor:null})
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Retry sources')!.click())
 await vi.waitFor(()=>expect(options()).toContain('Older show'))
 expect(node.textContent).not.toContain('Retry sources')
})
