// @vitest-environment jsdom
import React, { act, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import ResetPassword from '../src/pages/ResetPassword'
import { useDialog } from '../src/lib/reading'

let cleanup: (() => void) | undefined
function mount(element: React.ReactNode) {
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  act(() => root.render(element))
  cleanup = () => { act(() => root.unmount()); node.remove() }
  return node
}
afterEach(() => { cleanup?.(); cleanup=undefined; vi.unstubAllGlobals(); window.history.replaceState(null, '', '/'); sessionStorage.clear(); localStorage.clear() })

it('retains recovery token through Strict Mode and strips it from the address', async () => {
  window.history.replaceState(null, '', '/reset-password#type=recovery&access_token=private-recovery-token')
  const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>({message:'updated'})}); vi.stubGlobal('fetch',fetch)
  const node = mount(<StrictMode><MemoryRouter><ResetPassword /></MemoryRouter></StrictMode>)
  expect(node.querySelectorAll('input[type="password"]').length).toBe(2)
  expect(window.location.hash).toBe('')
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0)
  await act(async () => { node.querySelector('form')!.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true})); await Promise.resolve() })
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer private-recovery-token')
  expect(node.textContent).toContain('Your password is updated')
})

it('shows a clear recovery option when a reset token is missing', () => {
  const node = mount(<MemoryRouter><ResetPassword /></MemoryRouter>)
  expect(node.textContent).toContain('missing or expired')
  expect(node.querySelector('form')).toBeNull()
})

it('traps keyboard focus and restores the previous control when a dialog closes', () => {
  const opener = document.createElement('button'); document.body.append(opener); opener.focus()
  const close = vi.fn()
  function Dialog() { useDialog(true, close); return <div role="dialog"><button>First</button><button>Last</button></div> }
  const node = mount(<Dialog />)
  const buttons = node.querySelectorAll('button')
  expect(document.activeElement).toBe(buttons[0])
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}))
  expect(document.activeElement).toBe(buttons[1])
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  expect(close).toHaveBeenCalledOnce()
  cleanup?.(); cleanup=undefined
  expect(document.activeElement).toBe(opener); opener.remove()
})
