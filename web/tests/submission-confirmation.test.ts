// @vitest-environment jsdom
import {beforeEach,afterEach,expect,it,vi} from 'vitest'
import {generateVideoNote} from '../src/lib/api'
import {clearTokens} from '../src/lib/auth'
beforeEach(()=>{clearTokens();localStorage.clear();sessionStorage.clear()})
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()})
const request={url:'https://www.bilibili.com/video/BV1234567890',platform:'bilibili',skip_existing:true}
it('confirms a lost acknowledgement using an owned read without replaying the POST',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(Response.json({task_id:'accepted',status:'transcribing'}))
  vi.stubGlobal('fetch',fetch)
  expect(await generateVideoNote(request)).toEqual({task_id:'accepted'})
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[0][1].method).toBe('POST')
  expect(fetch.mock.calls[1][0]).toContain('/submission?')
  expect(fetch.mock.calls[1][1].method).toBeUndefined()
})
it('does not report acceptance when the lookup has no queued task',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(Response.json({task_id:null}))
  vi.stubGlobal('fetch',fetch)
  await expect(generateVideoNote(request)).rejects.toThrow('Failed to fetch')
  expect(fetch).toHaveBeenCalledTimes(2)
})
it('reconciles a timed-out POST and never retries processing',async()=>{
  vi.useFakeTimers()
  const fetch=vi.fn().mockImplementationOnce(()=>new Promise(()=>{})).mockResolvedValueOnce(Response.json({task_id:'queued',status:'pending'}))
  vi.stubGlobal('fetch',fetch)
  const result=generateVideoNote(request)
  await vi.advanceTimersByTimeAsync(60000)
  expect(await result).toEqual({task_id:'queued'})
  expect(fetch).toHaveBeenCalledTimes(2)
})
it('does not reconcile an unrelated regenerate operation or explicit API rejection',async()=>{
  const fetch=vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(Response.json({detail:'Invalid URL'},{status:400}))
  vi.stubGlobal('fetch',fetch)
  await expect(generateVideoNote({...request,skip_existing:false})).rejects.toThrow('Failed to fetch')
  await expect(generateVideoNote(request)).rejects.toThrow('Invalid URL')
  expect(fetch).toHaveBeenCalledTimes(2)
})
