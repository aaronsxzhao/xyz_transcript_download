// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {uploadLocalPodcastAudio,uploadVideoFile} from '../src/lib/api'
import {clearTokens} from '../src/lib/auth'

beforeEach(()=>{clearTokens();localStorage.clear();sessionStorage.clear()})
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()})

it('does not automatically create another audio episode after losing confirmation of a small upload',async()=>{
 const fetch=vi.fn(async(url:string)=>{
   if(url.endsWith('/upload-audio'))throw new TypeError('Failed to fetch')
   return Response.json({upload_id:'duplicate',chunk_size:1024,total_chunks:0})
 })
 vi.stubGlobal('fetch',fetch)
 await expect(uploadLocalPodcastAudio(new File(['audio'],'one.mp3'))).rejects.toThrow(/Local Uploads/)
 expect(fetch).toHaveBeenCalledTimes(1)
})

it.each(['audio','video'] as const)('does not restart a small %s upload after the account changes',async kind=>{
 let finish!:(response:Response)=>void
 const fetch=vi.fn((url:string)=>(url.endsWith('/upload-audio')||url.endsWith('/video-notes/upload'))?new Promise<Response>(resolve=>{finish=resolve}):Promise.resolve(Response.json({upload_id:'wrong-account',chunk_size:1024,total_chunks:0})))
 vi.stubGlobal('fetch',fetch)
 const file=new File(['media'],kind==='audio'?'one.mp3':'one.mp4')
 const pending=kind==='audio'?uploadLocalPodcastAudio(file):uploadVideoFile(file)
 const rejected=expect(pending).rejects.toMatchObject({name:'AbortError'})
 await vi.waitFor(()=>expect(finish).toBeDefined())
 clearTokens()
 finish(Response.json({file_id:'old',path:'/data/old'}))
 await rejected
 expect(fetch).toHaveBeenCalledTimes(1)
})

it('stops later video chunks when the account changes between successful chunks',async()=>{
 const fetch=vi.fn(async(url:string)=>url.endsWith('/init')?Response.json({upload_id:'one',chunk_size:5*1024*1024,total_chunks:2,recommended_concurrency:1}):Response.json({}))
 vi.stubGlobal('fetch',fetch)
 const progress=vi.fn((value:any)=>{if(value.phase==='uploading'&&value.uploadedChunks===1)clearTokens()})
 await expect(uploadVideoFile(new File([new Uint8Array(9*1024*1024)],'large.mp4'),progress)).rejects.toMatchObject({name:'AbortError'})
 expect(fetch.mock.calls.filter(([url])=>url.endsWith('/chunk'))).toHaveLength(1)
 expect(fetch.mock.calls.some(([url])=>url.endsWith('/complete'))).toBe(false)
})

it.each(['audio','video'] as const)('stops a backed-off %s chunk instead of retrying it under another account',async kind=>{
 vi.useFakeTimers()
 const fetch=vi.fn(async(url:string)=>url.endsWith('/init')?Response.json({upload_id:'one',chunk_size:10*1024*1024,total_chunks:1,recommended_concurrency:1}):new Response('Unavailable',{status:503}))
 vi.stubGlobal('fetch',fetch)
 const file=new File([new Uint8Array(9*1024*1024)],kind==='audio'?'large.mp3':'large.mp4')
 const pending=kind==='audio'?uploadLocalPodcastAudio(file):uploadVideoFile(file)
 const rejected=expect(pending).rejects.toMatchObject({name:'AbortError'})
 await vi.advanceTimersByTimeAsync(0)
 expect(fetch.mock.calls.filter(([url])=>url.endsWith('/chunk'))).toHaveLength(1)
 expect(vi.getTimerCount()).toBe(1) // only the retry backoff remains
 clearTokens()
 await vi.advanceTimersByTimeAsync(1500)
 await rejected
 expect(fetch.mock.calls.filter(([url])=>url.endsWith('/chunk'))).toHaveLength(1)
})

it('still switches a rejected oversized audio request to chunked upload',async()=>{
 const fetch=vi.fn(async(url:string)=>{
   if(url.endsWith('/upload-audio'))return new Response('Too large',{status:413})
   if(url.endsWith('/init'))return Response.json({upload_id:'one',chunk_size:1024,total_chunks:1})
   if(url.endsWith('/complete'))return Response.json({episode:{eid:'saved-once'}})
   return Response.json({})
 })
 vi.stubGlobal('fetch',fetch)
 await expect(uploadLocalPodcastAudio(new File(['audio'],'one.mp3'))).resolves.toMatchObject({episode:{eid:'saved-once'}})
 expect(fetch.mock.calls.filter(([url])=>url.endsWith('/complete'))).toHaveLength(1)
})
