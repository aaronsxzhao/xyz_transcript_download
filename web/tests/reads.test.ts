// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError, fetchSettings, fetchSummary, fetchVideoTasksByChannel } from '../src/lib/api'
import { clearTokens } from '../src/lib/auth'

beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('limits a stalled page read and allows a fresh retry', async () => {
  vi.useFakeTimers()
  let signal: AbortSignal | null | undefined
  const fetch = vi.fn((_url: string, options: RequestInit) => {
    signal = options.signal
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', fetch)
  const read = expect(fetchSettings()).rejects.toThrow('timed out')
  await vi.advanceTimersByTimeAsync(10000)
  await read
  expect(signal?.aborted).toBe(true)
  fetch.mockImplementationOnce(async () => Response.json({ llm_provider: 'groq' }))
  expect((await fetchSettings()).llm_provider).toBe('groq')
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('preserves missing-summary status separately from a server connection failure', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(Response.json({ detail: 'Summary not found' }, { status: 404 }))
    .mockResolvedValueOnce(Response.json({ detail: 'Please retry' }, { status: 503 })))
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
  await vi.advanceTimersByTimeAsync(10000)
  await result
})
