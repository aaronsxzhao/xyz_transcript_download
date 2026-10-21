// @vitest-environment jsdom
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { authFetch, fetchPodcasts } from '../src/lib/api'
import { clearTokens, getAccessToken, getAuthConfig, refreshToken, signIn } from '../src/lib/auth'
import { getCache, setCache } from '../src/lib/cache'
import { getAccountId, getPreference, setPreference } from '../src/lib/preferences'
import { getViewCount, markSeen } from '../src/lib/seen'

function seed(owner: string, token = 'old') {
  localStorage.setItem('xyz_remember_me', 'true')
  localStorage.setItem('xyz_access_token', token)
  localStorage.setItem('xyz_refresh_token', 'refresh-' + owner)
  localStorage.setItem('xyz_user', JSON.stringify({ id: owner, email: owner + '@example.com', authenticated: true }))
}

beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => vi.unstubAllGlobals())

describe('account isolation', () => {
  it('keeps cached notes, credentials and seen state separate across accounts', () => {
    seed('owner-a')
    const oldOwner = getAccountId()
    setCache('note', 'Private A note')
    setPreference('notion_api_key', 'Private A key')
    markSeen(['private-task'])
    seed('owner-b')
    expect(getCache('note')).toBeNull()
    expect(getPreference('notion_api_key')).toBeNull()
    expect(getViewCount('private-task')).toBe(0)
    setCache('note', 'Late A response', oldOwner)
    expect(getCache('note')).toBeNull()
  })

  it('fails closed if auth configuration cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unavailable', { status: 503 })))
    await expect(getAuthConfig()).rejects.toThrow('connection')
  })
})

describe('session refresh', () => {
  it('refreshes an expired JWT before sending parallel reads instead of waiting for 401s', async () => {
    const expired = `e30.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 60 }))}.signature`
    seed('owner-a', expired)
    const fetch = vi.fn(async (url: string, options: RequestInit = {}) => {
      if (url.endsWith('/auth/refresh')) return Response.json({ access_token: 'new', refresh_token: 'next', user_id: 'owner-a', email: 'a@example.com' })
      expect(new Headers(options.headers).get('Authorization')).toBe('Bearer new')
      return Response.json({ ok: true })
    })
    vi.stubGlobal('fetch', fetch)
    await Promise.all([authFetch('/api/podcasts'), authFetch('/api/jobs')])
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  })
  it('refreshes once for concurrent expired requests and retries with the new token', async () => {
    seed('owner-a')
    const fetch = vi.fn(async (url: string, options: RequestInit = {}) => {
      if (url.endsWith('/auth/refresh')) return Response.json({ access_token: 'new', refresh_token: 'next', user_id: 'owner-a', email: 'a@example.com' })
      return new Headers(options.headers).get('Authorization') === 'Bearer new'
        ? Response.json({ ok: true }) : new Response('', { status: 401 })
    })
    vi.stubGlobal('fetch', fetch)
    const responses = await Promise.all([authFetch('/api/podcasts'), authFetch('/api/jobs')])
    expect(responses.map(response => response.status)).toEqual([200, 200])
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/auth/refresh'))).toHaveLength(1)
  })

  it('does not restore a signed-out account when an old refresh finishes', async () => {
    seed('owner-a')
    let finish!: (response: Response) => void
    const pending = new Promise<Response>(resolve => { finish = resolve })
    vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/signin')
      ? Promise.resolve(Response.json({ access_token: 'b-access', refresh_token: 'b-refresh', user_id: 'owner-b', email: 'b@example.com' })) : pending))
    const oldRefresh = refreshToken()
    clearTokens()
    await signIn('b@example.com', 'password')
    finish(Response.json({ access_token: 'a-access', refresh_token: 'a-refresh', user_id: 'owner-a', email: 'a@example.com' }))
    expect(await oldRefresh).toBeNull()
    expect(getAccessToken()).toBe('b-access')
  })

  it('discards a response from an account that signed out during the request', async () => {
    seed('owner-a')
    let finish!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve })))
    const response = authFetch('/api/podcasts')
    clearTokens()
    finish(Response.json([{ title: 'Private A show' }]))
    await expect(response).rejects.toMatchObject({ name: 'AbortError' })
  })
})

it('shares an overlapping library read and invalidates cached data after a successful mutation', async () => {
  seed('owner-a')
  setCache('summary_one', 'old note')
  setCache('settings', {theme:'dark'})
  const fetch = vi.fn(async (url: string) => Response.json(url === '/api/podcasts' ? [{ pid: 'one' }] : { ok: true }))
  vi.stubGlobal('fetch', fetch)
  const [a, b] = await Promise.all([fetchPodcasts(), fetchPodcasts()])
  expect(a).toEqual(b)
  expect(fetch).toHaveBeenCalledOnce()
  await authFetch('/api/episodes/one', { method: 'DELETE' })
  expect(getCache('summary_one')).toBeNull()
  expect(getCache('settings')).toEqual({theme:'dark'})
})

it('uses only public bootstrap config from HTML without another network round trip', async () => {
  const node = document.createElement('script')
  node.id = 'xyz-auth-config'
  node.type = 'application/json'
  node.textContent = JSON.stringify({ supabase_enabled: true, supabase_url: 'https://example.supabase.co' })
  document.head.append(node)
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  try {
    expect((await getAuthConfig()).supabase_enabled).toBe(true)
    expect(fetch).not.toHaveBeenCalled()
  } finally { node.remove() }
})
