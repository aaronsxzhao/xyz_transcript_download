// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { takeStartupRead } from '../src/lib/startupReads'

afterEach(() => { delete window.__xyzStartupReads; vi.unstubAllGlobals() })
it('reuses an early read once, only for the same session and origin', async () => {
  const response = {body: JSON.stringify({private:'note-a'}),status:200,headers:new Headers()}
  window.__xyzStartupReads = new Map([['/api/settings', {token:'a', response:Promise.resolve(response)}]])
  expect(takeStartupRead('https://another-origin.invalid/api/settings','a')).toBeNull()
  expect(takeStartupRead('/api/settings','b')).toBeNull()
  window.__xyzStartupReads.set('/api/settings', {token:'a', response:Promise.resolve(response)})
  expect(await (await takeStartupRead('/api/settings','a'))?.json()).toEqual({private:'note-a'})
  expect(takeStartupRead('/api/settings','a')).toBeNull()
})
it('falls back cleanly when the early request could not connect', async () => {
  window.__xyzStartupReads = new Map([['/api/settings',{token:'a',response:Promise.resolve(null)}]])
  expect(await takeStartupRead('/api/settings','a')).toBeNull()
})

it('bounds stalled session verification without logging the user out', async () => {
  const {clearTokens,getCurrentUser,getAccessToken}=await import('../src/lib/auth')
  clearTokens();localStorage.setItem('xyz_access_token','synthetic-token')
  vi.useFakeTimers()
  vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})))
  const pending=expect(getCurrentUser()).rejects.toThrow('timed out')
  await vi.advanceTimersByTimeAsync(10000);await pending
  expect(getAccessToken()).toBe('synthetic-token')
  vi.stubGlobal('fetch',vi.fn(async()=>Response.json({id:'bench',email:'bench@example.com',authenticated:true})))
  expect((await getCurrentUser())?.id).toBe('bench')
  vi.useRealTimers();clearTokens()
})
