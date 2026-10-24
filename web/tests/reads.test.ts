// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError, fetchSettings, fetchSummary, fetchVideoTasksByChannel, removePodcast, deleteEpisode, fetchNotionPages, exportMarkdownToNotion } from '../src/lib/api'
import { clearTokens } from '../src/lib/auth'

beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it.each([removePodcast,deleteEpisode])('preserves a rejected deletion status and its recovery message',async remove=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({detail:'Could not confirm deletion. Refresh before retrying.'},{status:503})))
 await expect(remove('owned-id')).rejects.toMatchObject({status:503,message:'Could not confirm deletion. Refresh before retrying.'})
})
it('keeps successful deletion responses compatible',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>Response.json({message:'Deleted'})))
 await expect(removePodcast('owned-id')).resolves.toBeUndefined()
 await expect(deleteEpisode('owned-id')).resolves.toEqual({message:'Deleted'})
})
it.each(['search','export'])('keeps Notion %s proxy errors readable with their status',async kind=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>new Response('Upstream unavailable',{status:502})))
 const pending=kind==='search'?fetchNotionPages():exportMarkdownToNotion('# Note','Title','parent')
 await expect(pending).rejects.toMatchObject({status:502,message:expect.stringContaining('Upstream unavailable')})
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
