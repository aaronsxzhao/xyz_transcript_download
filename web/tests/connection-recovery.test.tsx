// @vitest-environment jsdom
import React, { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../src/contexts/AuthContext'
import LoadError from '../src/components/LoadError'
import { fetchLibrary, fetchSettings, authFetch } from '../src/lib/api'
import { clearTokens } from '../src/lib/auth'

vi.mock('../src/lib/websocket', () => ({connectWebSocket: vi.fn(), disconnectWebSocket: vi.fn()}))
let root: ReturnType<typeof createRoot> | undefined
let node: HTMLDivElement | undefined
beforeEach(() => { clearTokens(); localStorage.clear(); sessionStorage.clear() })
afterEach(() => {
  if (root) act(() => root!.unmount())
  node?.remove(); root = undefined; node = undefined
  document.getElementById('xyz-auth-config')?.remove()
  vi.useRealTimers(); vi.unstubAllGlobals()
})

it('recovers a transient read failure without requiring a manual retry', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(Response.json({llm_provider:'groq'}))
  vi.stubGlobal('fetch', fetch)
  expect((await fetchSettings()).llm_provider).toBe('groq')
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('does not retry a cancelled read or resubmit an uncertain mutation', async () => {
  const controller = new AbortController()
  const fetch = vi.fn().mockImplementation(async () => {
    controller.abort()
    throw new TypeError('Failed to fetch')
  })
  vi.stubGlobal('fetch', fetch)
  await expect(fetchLibrary('q=old','',controller.signal)).rejects.toMatchObject({name:'AbortError'})
  expect(fetch).toHaveBeenCalledTimes(1)
  await expect(authFetch('/api/process', {method:'POST'})).rejects.toThrow('Failed to fetch')
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('does not repeat an ambiguous token refresh while retrying a safe read', async () => {
  const expired = `e30.${btoa(JSON.stringify({exp:1}))}.signature`
  localStorage.setItem('xyz_access_token',expired)
  localStorage.setItem('xyz_refresh_token','synthetic-refresh')
  const fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
  vi.stubGlobal('fetch',fetch)
  await expect(fetchSettings()).rejects.toThrow('Failed to fetch')
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][0]).toContain('/auth/refresh')
})

function Probe() {
  const auth = useAuth() as ReturnType<typeof useAuth> & {connectionError?: string}
  const [failed, setFailed] = useState(true)
  return <><span data-session-error>{auth.connectionError}</span><span>{auth.user?.id}</span>
    {failed && <LoadError message="Loading timed out. Please retry." onRetry={() => setFailed(false)}/>}</>
}

async function mountOfflineSession() {
  localStorage.setItem('xyz_access_token','synthetic-token')
  localStorage.setItem('xyz_user',JSON.stringify({id:'owner',email:'',authenticated:true}))
  const config = document.createElement('script'); config.id='xyz-auth-config'; config.type='application/json'
  config.textContent=JSON.stringify({supabase_enabled:true,supabase_url:null}); document.head.append(config)
  let reachable = false
  const fetch = vi.fn(async () => reachable
    ? Response.json({id:'owner',email:'',authenticated:true})
    : Response.json({detail:'Unavailable'}, {status:503}))
  vi.stubGlobal('fetch',fetch)
  node=document.createElement('div'); document.body.append(node); root=createRoot(node)
  await act(async () => { root!.render(<AuthProvider><Probe/></AuthProvider>) })
  return {fetch, recover: () => { reachable = true }}
}

it('rechecks failed session verification when the connection returns', async () => {
  const state = await mountOfflineSession()
  expect(node!.querySelector('[data-session-error]')!.textContent).not.toBe('')
  state.recover()
  await act(async () => { window.dispatchEvent(new Event('online')) })
  expect(node!.querySelector('[data-session-error]')!.textContent).toBe('')
  expect(node!.querySelector('[role=alert]')).toBeNull()
  expect(node!.textContent).toContain('owner')
})

it('one retry action recovers both the failed page and session check', async () => {
  const state = await mountOfflineSession()
  state.recover()
  await act(async () => { [...node!.querySelectorAll('button')].find(b => b.textContent==='Retry')!.click() })
  expect(node!.querySelector('[data-session-error]')!.textContent).toBe('')
  expect(node!.querySelector('[role=alert]')).toBeNull()
})

it('recovers when a mobile browser becomes visible, without reloading healthy or hidden pages', async () => {
  const state = await mountOfflineSession()
  const initial = state.fetch.mock.calls.length
  let visibility = 'hidden'
  Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>visibility})
  try {
    state.recover()
    await act(async()=>document.dispatchEvent(new Event('visibilitychange')))
    expect(state.fetch).toHaveBeenCalledTimes(initial)
    visibility='visible'
    await act(async()=>document.dispatchEvent(new Event('visibilitychange')))
    expect(node!.querySelector('[data-session-error]')!.textContent).toBe('')
    expect(node!.querySelector('[role=alert]')).toBeNull()
    const recovered=state.fetch.mock.calls.length
    await act(async()=>document.dispatchEvent(new Event('visibilitychange')))
    expect(state.fetch).toHaveBeenCalledTimes(recovered)
  } finally { delete (document as any).visibilityState }
})
