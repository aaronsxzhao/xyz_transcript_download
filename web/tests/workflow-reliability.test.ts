// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearTokens, getAccessToken, getAuthGeneration, requestAuth, signIn, watchStoredSession } from '../src/lib/auth'
import { fetchSummary, uploadVideoFile } from '../src/lib/api'
import { fetchWithCache, setCache } from '../src/lib/cache'
import { extractNoteToc, prepareNoteMarkdown } from '../src/lib/noteMarkdown'

beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('bounds login and recovery requests including a stalled response body', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({text: () => new Promise(() => {})}))
  const result = expect(requestAuth('password-reset', {method:'POST'})).rejects.toThrow('timed out')
  await vi.advanceTimersByTimeAsync(10000)
  await result
})

it('does not sign an account back in after logout while login was pending', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve })))
  const login = signIn('a@example.com', 'password')
  clearTokens()
  finish(Response.json({user_id:'a',email:'a@example.com',access_token:'late',refresh_token:'late'}))
  await expect(login).rejects.toMatchObject({name:'AbortError'})
  expect(getAccessToken()).toBeNull()
})

it('invalidates the request generation on cross-tab account changes, not same-owner refresh', () => {
  localStorage.setItem('xyz_user', JSON.stringify({id:'a'}))
  const stop = watchStoredSession()
  const generation = getAuthGeneration()
  const change = () => window.dispatchEvent(new StorageEvent('storage', {key:'xyz_user',storageArea:localStorage}))
  change()
  expect(getAuthGeneration()).toBe(generation)
  localStorage.setItem('xyz_user', JSON.stringify({id:'b'})); change()
  expect(getAuthGeneration()).toBe(generation + 1)
  localStorage.removeItem('xyz_user'); change()
  expect(getAuthGeneration()).toBe(generation + 2)
  stop()
})

function mockUpload(finish: () => Promise<Response>) {
  const fetch = vi.fn(async (url: string) => {
    if (url.endsWith('/init')) return Response.json({upload_id:'test',chunk_size:10*1024*1024,total_chunks:1})
    if (url.includes('/status?')) return Response.json({upload_id:'test',phase:'assembling',percent:100})
    if (url.endsWith('/complete')) return finish()
    return Response.json({})
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}
const file = () => new File([new Uint8Array(9*1024*1024)], 'sample.mp4')

it.each(['network', 'malformed'])('stops assembly polling after %s finalization failure', async failure => {
  vi.useFakeTimers()
  const fetch = mockUpload(async () => {
    if (failure === 'network') throw new TypeError('Failed to fetch')
    return new Response('invalid json')
  })
  await expect(uploadVideoFile(file())).rejects.toThrow()
  const requests = fetch.mock.calls.length
  await vi.advanceTimersByTimeAsync(30000)
  expect(fetch).toHaveBeenCalledTimes(requests)
})

it('successful finalization does not wait for a stuck status poll', async () => {
  vi.useFakeTimers()
  const fetch = mockUpload(async () => Response.json({file_id:'test',path:'/data/uploads/test.mp4'}))
  fetch.mockImplementation(async (url: string) => {
    if (url.endsWith('/init')) return Response.json({upload_id:'test',chunk_size:10*1024*1024,total_chunks:1})
    if (url.includes('/status?')) return new Promise<Response>(() => {})
    if (url.endsWith('/complete')) return Response.json({file_id:'test',path:'/data/uploads/test.mp4'})
    return Response.json({})
  })
  await expect(uploadVideoFile(file())).resolves.toMatchObject({file_id:'test'})
  expect(vi.getTimerCount()).toBe(0)
})

it('preserves ordinary Markdown separators and prose called Table of Contents', () => {
  for (const source of ['Before\n\n---\n\nAfter', '## Table of Contents\n\nThis explains the chapter.\n\n## Next\nText', '```\n## 目录\n- item\n```']) {
    expect(prepareNoteMarkdown(source)).toBe(source)
  }
  expect(prepareNoteMarkdown('# Title\n\n## 目录\n\n- [Title](#title)\n')).toBe('# Title\n\n')
  expect(extractNoteToc('## Café &amp; 茶\n\n## Café &amp; 茶').map(h => h.slug)).toEqual(['café-茶','café-茶-1'])
})


it('rejects a response whose body finishes after the account changes', async () => {
  let body!: (value: unknown) => void
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true, text: () => new Promise(resolve => { body = resolve })}))
  const request = fetchSummary('account-race')
  await vi.waitFor(() => expect(body).toBeDefined())
  clearTokens()
  body(JSON.stringify({title:'Old account'}))
  await expect(request).rejects.toMatchObject({name:'AbortError'})
})

it('does not return the old account cache when an in-flight refresh fails', async () => {
  localStorage.setItem('xyz_user', JSON.stringify({id:'a'}))
  setCache('race', {title:'Private A'})
  let fail!: (error: Error) => void
  const request = fetchWithCache('race', () => new Promise((_, reject) => { fail = reject }))
  localStorage.setItem('xyz_user', JSON.stringify({id:'b'}))
  fail(new Error('Network failure'))
  await expect(request).rejects.toMatchObject({name:'AbortError'})
})
