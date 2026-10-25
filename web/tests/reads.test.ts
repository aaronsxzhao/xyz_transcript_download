// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError, parseApiResponseAsJson, fetchSettings, fetchSummary, fetchVideoTasksByChannel, removePodcast, deleteEpisode, fetchNotionPages, exportMarkdownToNotion, exportToNotion } from '../src/lib/api'
import { clearTokens } from '../src/lib/auth'

beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it.each([200,502,503,504])('explains an HTML gateway response (%s) without exposing its body', async status => {
 const html='<!DOCTYPE html><!-- private upstream details --><html><body>private-key-and-address</body></html>'
 const response=new Response(html,{status,headers:{'Content-Type':'text/html','CF-Ray':'123abc-IAD'}})
 const failed=await parseApiResponseAsJson(response,'Connection test failed').catch(error=>error)
 expect(failed).toBeInstanceOf(ApiError)
 expect(failed.status).toBe(status)
 expect(failed.message).toContain('website gateway')
 expect(failed.message).toContain('123abc-IAD')
 expect(failed.message).not.toContain('DOCTYPE')
 expect(failed.message).not.toContain('private-')
});
it('recognizes HTML without a content type and preserves real provider JSON errors', async()=>{
 await expect(parseApiResponseAsJson(new Response('<html>Bad gateway</html>',{status:502}),'Test')).rejects.toThrow('website gateway')
 await expect(parseApiResponseAsJson(Response.json({detail:'Provider rejected model access'},{status:502}),'Test')).rejects.toMatchObject({status:502,message:'Provider rejected model access'})
});

it.each([removePodcast,deleteEpisode])('preserves a rejected deletion status and its recovery message',async remove=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({detail:'Could not confirm deletion. Refresh before retrying.'},{status:503})))
 await expect(remove('owned-id')).rejects.toMatchObject({status:503,message:'Could not confirm deletion. Refresh before retrying.'})
})
it('keeps successful deletion responses compatible',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>Response.json({message:'Deleted'})))
 await expect(removePodcast('owned-id')).resolves.toBeUndefined()
 await expect(deleteEpisode('owned-id')).resolves.toEqual({message:'Deleted'})
})
it.each(['search','export','saved-video'])('keeps Notion %s proxy errors readable with their status',async kind=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>new Response('Upstream unavailable',{status:502})))
 const pending=kind==='search'?fetchNotionPages():kind==='saved-video'?exportToNotion('task','parent'):exportMarkdownToNotion('# Note','Title','parent')
 await expect(pending).rejects.toMatchObject({status:502,message:expect.stringContaining('Upstream unavailable')})
})
it.each(['markdown','saved-video'])('waits for a long Notion %s export without replaying it',async kind=>{
 vi.useFakeTimers()
 let finish!:(value:Response)=>void
 const fetch=vi.fn().mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 vi.stubGlobal('fetch',fetch)
 const pending=kind==='markdown'?exportMarkdownToNotion('# Note','Title','parent'):exportToNotion('task','parent')
 await vi.advanceTimersByTimeAsync(65000)
 expect(fetch).toHaveBeenCalledOnce()
 await vi.advanceTimersByTimeAsync(1000)
 finish(Response.json({url:'https://notion.so/note',page_id:'note',title:'Title'}))
 await expect(pending).resolves.toMatchObject({page_id:'note'})
})
it('bounds an unconfirmed Notion export and never resends the mutation',async()=>{
 vi.useFakeTimers()
 let signal:AbortSignal|undefined|null
 const fetch=vi.fn((_url:string,options:RequestInit)=>{signal=options.signal;return new Promise(()=>{})})
 vi.stubGlobal('fetch',fetch)
 const pending=expect(exportMarkdownToNotion('# Note','Title','parent')).rejects.toThrow('may still be running')
 await vi.advanceTimersByTimeAsync(120000)
 await pending
 expect(signal?.aborted).toBe(true);expect(fetch).toHaveBeenCalledOnce()
})
it('does not treat an incomplete export response as a successful receipt',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({message:'Accepted'})))
 await expect(exportMarkdownToNotion('# Note','Title','parent')).rejects.toThrow('incomplete export confirmation')
})

it('limits a stalled page read and allows a fresh retry', async () => {
  vi.useFakeTimers()
  let signal: AbortSignal | null | undefined
  const fetch = vi.fn((_url: string, options: RequestInit) => {
    signal = options.signal
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', fetch)
  const read = expect(fetchSettings()).rejects.toThrow('timed out')
  await vi.advanceTimersByTimeAsync(20000)
  await read
  expect(signal?.aborted).toBe(true)
  fetch.mockImplementationOnce(async () => Response.json({ llm_provider: 'groq' }))
  expect((await fetchSettings()).llm_provider).toBe('groq')
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('preserves missing-summary status separately from a server connection failure', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(Response.json({ detail: 'Summary not found' }, { status: 404 }))
    .mockImplementation(async()=>Response.json({ detail: 'Please retry' }, { status: 503 })))
  await expect(fetchSummary('missing')).rejects.toMatchObject({ status: 404 })
  await expect(fetchSummary('existing')).rejects.toMatchObject({ status: 503 })
  expect(new ApiError('message', 503)).toBeInstanceOf(Error)
})

it('limits response body reads too and shares overlapping channel requests', async () => {
  vi.useFakeTimers()
  const fetch = vi.fn().mockResolvedValue({ text: () => new Promise(() => {}) })
  vi.stubGlobal('fetch', fetch)
  const a = fetchVideoTasksByChannel('youtube', 'A + B')
  const b = fetchVideoTasksByChannel('youtube', 'A + B')
  const result = expect(Promise.all([a, b])).rejects.toThrow('timed out')
  expect(fetch).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(20000)
  await result
})
