// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {Blob as NativeBlob} from 'node:buffer'
import {downloadArchive,NoteRecovery} from '../src/components/DataRecovery'

const mocks=vi.hoisted(()=>({fetch:vi.fn(),generation:0,clear:vi.fn()}))
vi.mock('../src/lib/api',()=>({authFetch:mocks.fetch}))
vi.mock('../src/lib/auth',()=>({getAuthGeneration:()=>mocks.generation}))
vi.mock('../src/lib/cache',()=>({clearCache:mocks.clear}))
const bytes=new Uint8Array([80,75,3,4,255,128,0,195,40,127])
const create=vi.fn(),revoke=vi.fn(),click=vi.fn()
let root:ReturnType<typeof createRoot>|undefined,node:HTMLDivElement|undefined
beforeEach(()=>{
 vi.useFakeTimers();vi.clearAllMocks();mocks.generation=0
 vi.stubGlobal('Blob',NativeBlob)
 const NativeURL=URL
 vi.stubGlobal('URL',class extends NativeURL {static createObjectURL=create.mockReturnValue('blob:synthetic-backup');static revokeObjectURL=revoke})
 vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(click)
})
afterEach(()=>{if(root)act(()=>root!.unmount());node?.remove();root=undefined;node=undefined;vi.clearAllTimers();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals()})

it('waits for a slow archive once and downloads the original bytes',async()=>{
 let finish!:(response:Response)=>void
 mocks.fetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=downloadArchive('/api/maintenance/backup','backup.zip')
 await vi.advanceTimersByTimeAsync(65000)
 expect(mocks.fetch).toHaveBeenCalledOnce()
 finish(new Response(bytes,{headers:{'Content-Type':'application/zip','X-Missing-Images':'2'}}))
 expect(await pending).toContain('2 unavailable images')
 expect(new Uint8Array(await create.mock.calls[0][0].arrayBuffer())).toEqual(bytes)
 expect(click).toHaveBeenCalledOnce()
 expect(document.querySelector('a[download]')).toBeNull()
 await vi.advanceTimersByTimeAsync(30000)
 expect(revoke).toHaveBeenCalledWith('blob:synthetic-backup')
})

it('bounds a stalled backup without automatically rebuilding it',async()=>{
 mocks.fetch.mockImplementationOnce(()=>new Promise(()=>{}))
 const rejected=expect(downloadArchive('/api/maintenance/backup','backup.zip')).rejects.toThrow('Backup preparation timed out')
 await vi.advanceTimersByTimeAsync(180000)
 await rejected
 expect(mocks.fetch).toHaveBeenCalledOnce()
 expect(mocks.fetch.mock.calls[0][1].signal.aborted).toBe(true)
 expect(create).not.toHaveBeenCalled()
})

it.each([200,502])('does not download an HTTP %s HTML error page as a ZIP backup',async status=>{
 mocks.fetch.mockResolvedValueOnce(new Response('<html>Upstream unavailable</html>',{status}))
 await expect(downloadArchive('/api/maintenance/backup','backup.zip')).rejects.toThrow(status===200?'did not return a ZIP':'HTTP 502')
 expect(create).not.toHaveBeenCalled();expect(mocks.fetch).toHaveBeenCalledOnce()
})

it('does not download a previous account archive after the session changes',async()=>{
 let finish!:(response:Response)=>void
 mocks.fetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const rejected=expect(downloadArchive('/api/maintenance/backup','backup.zip')).rejects.toMatchObject({name:'AbortError'})
 mocks.generation++
 finish(new Response(bytes))
 await rejected
 expect(create).not.toHaveBeenCalled()
})

it('serializes slow screenshot status checks and clears a recovered network error',async()=>{
 let finish!:(response:Response)=>void
 mocks.fetch.mockResolvedValueOnce(Response.json({status:'running'}))
   .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
   .mockResolvedValueOnce(new Response('Unavailable',{status:503}))
   .mockResolvedValueOnce(Response.json({status:'completed',message:'Screenshots restored.'}))
 const restored=vi.fn();node=document.createElement('div');document.body.append(node);root=createRoot(node)
 await act(async()=>root!.render(<MemoryRouter><NoteRecovery id="note" expanded onRestored={restored}/></MemoryRouter>))
 await act(async()=>[...node!.querySelectorAll('button')].find(b=>b.textContent==='Repair screenshots')!.click())
 await act(async()=>vi.advanceTimersByTimeAsync(16000))
 expect(mocks.fetch).toHaveBeenCalledTimes(2)
 await act(async()=>finish(Response.json({status:'running'})))
 await act(async()=>vi.advanceTimersByTimeAsync(4000))
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Could not check screenshot repair')
 await act(async()=>vi.advanceTimersByTimeAsync(4000))
 expect(node.textContent).toContain('Screenshots restored.')
 expect(node.querySelector('[role=alert]')).toBeNull()
 expect(restored).toHaveBeenCalledOnce();expect(mocks.clear).toHaveBeenCalledOnce()
 await act(async()=>vi.advanceTimersByTimeAsync(20000))
 expect(mocks.fetch).toHaveBeenCalledTimes(4)
})

it('ignores a previous account screenshot result instead of refreshing the next account reader',async()=>{
 let finish!:(response:Response)=>void
 mocks.fetch.mockResolvedValueOnce(Response.json({status:'running'})).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const restored=vi.fn();node=document.createElement('div');document.body.append(node);root=createRoot(node)
 await act(async()=>root!.render(<MemoryRouter><NoteRecovery id="note" expanded onRestored={restored}/></MemoryRouter>))
 await act(async()=>[...node!.querySelectorAll('button')].find(b=>b.textContent==='Repair screenshots')!.click())
 await act(async()=>vi.advanceTimersByTimeAsync(4000))
 mocks.generation++
 await act(async()=>finish(Response.json({status:'completed',message:'Old account report'})))
 expect(restored).not.toHaveBeenCalled();expect(mocks.clear).not.toHaveBeenCalled()
 expect(node.textContent).not.toContain('Old account report')
 await act(async()=>vi.advanceTimersByTimeAsync(20000))
 expect(mocks.fetch).toHaveBeenCalledTimes(2)
})

it('reconciles a lost repair submission response without submitting twice',async()=>{
 mocks.fetch.mockImplementationOnce(()=>new Promise(()=>{}))
   .mockResolvedValueOnce(Response.json({status:'completed',message:'Screenshots restored.'}))
 const restored=vi.fn();node=document.createElement('div');document.body.append(node);root=createRoot(node)
 await act(async()=>root!.render(<MemoryRouter><NoteRecovery id="note" expanded onRestored={restored}/></MemoryRouter>))
 await act(async()=>[...node!.querySelectorAll('button')].find(b=>b.textContent==='Repair screenshots')!.click())
 await act(async()=>vi.advanceTimersByTimeAsync(20000))
 expect(node.textContent).toContain('Checking whether screenshot repair started')
 await act(async()=>vi.advanceTimersByTimeAsync(4000))
 expect(restored).toHaveBeenCalledOnce()
 expect(mocks.fetch.mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(1)
 expect(node.textContent).toContain('Screenshots restored')
})
