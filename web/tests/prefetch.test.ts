// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { authFetch, fetchVideoTask } from '../src/lib/api'
import { clearTokens } from '../src/lib/auth'
import { CacheKeys, getCache } from '../src/lib/cache'
import { prefetchSummary, prefetchVideoNote } from '../src/lib/summaryPrefetch'

vi.mock('../src/lib/pages', () => ({ preloadPage: vi.fn() }))
beforeEach(() => {
  clearTokens(); localStorage.clear(); sessionStorage.clear()
  localStorage.setItem('xyz_user', JSON.stringify({ id: 'owner', authenticated: true }))
  localStorage.setItem('xyz_access_token', 'valid')
})
afterEach(() => vi.unstubAllGlobals())

it('bounds speculative reads while allowing the opened note to load and share its request', async () => {
  const complete: Array<(response: Response) => void> = []
  const fetch = vi.fn(() => new Promise<Response>(resolve => complete.push(resolve)))
  vi.stubGlobal('fetch', fetch)
  prefetchVideoNote('first'); prefetchVideoNote('first'); prefetchVideoNote('second'); prefetchVideoNote('third')
  expect(fetch).toHaveBeenCalledTimes(2)
  const foreground = fetchVideoTask('first')
  expect(fetch).toHaveBeenCalledTimes(2)
  complete[0](Response.json({ id: 'first', status: 'success', markdown: 'Saved note' }))
  complete[1](Response.json({ id: 'second', status: 'success', markdown: 'Another note' }))
  await foreground
  await vi.waitFor(() => expect(getCache(CacheKeys.VIDEO_NOTE('first'))).toMatchObject({ markdown: 'Saved note' }))
  await new Promise(resolve => setTimeout(resolve, 0))
})

it('discards a prefetch when a mutation invalidates the note', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/retry') ? Promise.resolve(Response.json({ ok: true }))
    : new Promise<Response>(resolve => { finish = resolve })) )
  prefetchVideoNote('regenerating')
  await authFetch('/api/video-notes/tasks/regenerating/retry', { method: 'POST' })
  finish(Response.json({ id: 'regenerating', status: 'success', markdown: 'Old note' }))
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(getCache(CacheKeys.VIDEO_NOTE('regenerating'))).toBeNull()
})

it('does not write an old account response into a new account cache', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve })))
  prefetchSummary('private')
  clearTokens()
  localStorage.setItem('xyz_user', JSON.stringify({ id: 'another', authenticated: true }))
  finish(Response.json({ episode_id: 'private', overview: 'Private old account content' }))
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(getCache(CacheKeys.SUMMARY('private'))).toBeNull()
})
