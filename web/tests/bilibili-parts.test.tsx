// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
const mocks=vi.hoisted(()=>({fetch:vi.fn()}))
vi.mock('../src/lib/api',()=>({authFetch:mocks.fetch}))
vi.mock('../src/lib/auth',()=>({getAuthGeneration:()=>1}))
import BilibiliParts from '../src/components/video/BilibiliParts'
let node:HTMLDivElement,root:ReturnType<typeof createRoot>,parts:any[]
const response=(body:unknown,ok=true)=>({ok,json:async()=>body})
const metadata={bilibili_part:{page:2,cid:'2',duration:60,title:'P2',url:'https://www.bilibili.com/video/BVtest?p=2'},bilibili_parts:[1,2,3,4].map(page=>({page,title:`P${page} Chapter`,url:`https://www.bilibili.com/video/BVtest?p=${page}`}))}
beforeEach(()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true)
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
 parts=metadata.bilibili_parts.map(part=>({...part,status:part.page===2?'success':'not_started',progress:0,task_id:part.page===2?'current':null}))
 mocks.fetch.mockReset()
 mocks.fetch.mockImplementation(async(url:string,options?:RequestInit)=>{
  if(options?.method==='POST'){
   const page=Number(url.match(/parts\/(\d+)\/process/)![1]);parts=parts.map(part=>part.page===page?{...part,status:'pending',task_id:`part-${page}`}:part)
   return response({task_id:`part-${page}`})
  }
  return response({parts:parts.map(part=>({...part}))})
 })
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.unstubAllGlobals()})
const mount=()=>act(async()=>root.render(<MemoryRouter initialEntries={["/videos/current"]}><Routes><Route path="/videos/:taskId" element={<BilibiliParts metadata={metadata}/>}/></Routes></MemoryRouter>))
const button=(text:string)=>[...node.querySelectorAll('button')].find(button=>button.textContent!.startsWith(text))!
const posts=()=>mocks.fetch.mock.calls.filter(([,options])=>options?.method==='POST')
it('shows all parts, skips the current part and submits only selected other parts',async()=>{
 await mount()
 expect(node.textContent).toContain('Collection · 4 parts')
 expect(node.querySelectorAll('input[type=checkbox]')).toHaveLength(4)
 expect((node.querySelectorAll('input')[1] as HTMLInputElement).disabled).toBe(true)
 act(()=>button('Select unprocessed').click())
 expect(button('Process selected').textContent).toContain('(3)')
 await act(async()=>button('Process selected').click())
 expect(posts().map(([url])=>url)).toEqual([1,3,4].map(page=>`/api/video-notes/collections/current/parts/${page}/process`))
 expect(node.textContent).toContain('3 of 3 confirmed')
 expect(node.querySelector('a[href="/videos/part-3"]')?.textContent).toBe('View progress')
 expect(node.querySelector('a[href="/videos/current"]')?.textContent).toBe('Read summary')
})
it('stops on uncertain acknowledgement and retains only unconfirmed selections for retry',async()=>{
 const original=mocks.fetch.getMockImplementation()!
 mocks.fetch.mockImplementation((url,options)=>url.endsWith('/3/process')?Promise.reject(new Error('Connection interrupted')):original(url,options))
 await mount();act(()=>button('Select unprocessed').click())
 await act(async()=>button('Process selected').click())
 expect(posts()).toHaveLength(2)
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Remaining parts were not submitted')
 expect(button('Process selected').disabled).toBe(true)
 expect((node.querySelectorAll('input')[0] as HTMLInputElement).checked).toBe(false)
 expect((node.querySelectorAll('input')[2] as HTMLInputElement).checked).toBe(true)
 mocks.fetch.mockImplementation(original)
 await act(async()=>button('Refresh statuses').click())
 await act(async()=>button('Process selected').click())
 expect(posts().filter(([url])=>url.endsWith('/1/process'))).toHaveLength(1)
 expect(posts().some(([url])=>url.endsWith('/4/process'))).toBe(true)
})
it('does not submit further parts after navigating away during admission',async()=>{
 let finish:(value:unknown)=>void=()=>{}
 const original=mocks.fetch.getMockImplementation()!
 mocks.fetch.mockImplementation((url,options)=>options?.method==='POST'?new Promise(resolve=>{finish=resolve}):original(url,options))
 await mount();act(()=>button('Select unprocessed').click())
 await act(async()=>button('Process selected').click())
 await act(async()=>root.render(<p>Another page</p>))
 await act(async()=>finish(response({task_id:'part-1'})))
 expect(posts()).toHaveLength(1)
})

it('bounds a stalled status body and lets the user retry',async()=>{
 vi.useFakeTimers()
 mocks.fetch.mockResolvedValue({ok:true,json:()=>new Promise(()=>{})})
 await mount()
 await act(async()=>vi.advanceTimersByTimeAsync(15000))
 expect(node.querySelector('[role=alert]')?.textContent).toContain('timed out')
 expect(button('Refresh statuses').disabled).toBe(false)
 expect(mocks.fetch).toHaveBeenCalledTimes(1)
 vi.useRealTimers()
})
it('times out an unconfirmed submission without submitting the remaining parts',async()=>{
 vi.useFakeTimers()
 await mount();act(()=>button('Select unprocessed').click())
 mocks.fetch.mockImplementation(()=>new Promise(()=>{}))
 await act(async()=>button('Process selected').click())
 await act(async()=>vi.advanceTimersByTimeAsync(60000))
 expect(posts()).toHaveLength(1)
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Queue confirmation timed out')
 expect(button('Refresh statuses').disabled).toBe(false)
 expect(button('Process selected').disabled).toBe(true)
 vi.useRealTimers()
})
it('clears the previous collection immediately on account change',async()=>{
 await mount()
 expect(node.textContent).toContain('P1 Chapter')
 mocks.fetch.mockImplementation(()=>new Promise(()=>{}))
 await act(async()=>window.dispatchEvent(new Event('xyz:session-changed')))
 expect(node.textContent).not.toContain('P1 Chapter')
 expect(node.querySelectorAll('input')).toHaveLength(0)
})
