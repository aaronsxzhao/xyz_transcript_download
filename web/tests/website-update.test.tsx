// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach, beforeEach, expect, it, vi} from 'vitest'
import WebsiteUpdate from '../src/components/WebsiteUpdate'
import {applyWebsiteUpdate, hasWebsiteUpdate} from '../src/lib/publicCache'

vi.mock('../src/lib/publicCache', () => ({applyWebsiteUpdate:vi.fn(),hasWebsiteUpdate:vi.fn()}))
let node:HTMLDivElement, root:ReturnType<typeof createRoot> | undefined
beforeEach(() => {
  vi.useFakeTimers();vi.resetAllMocks()
  vi.mocked(hasWebsiteUpdate).mockReturnValue(true)
  vi.spyOn(navigator,'onLine','get').mockReturnValue(true)
  node=document.createElement('div');document.body.append(node)
  root=createRoot(node)
})
afterEach(() => {
  if(root)act(() => root!.unmount())
  node.remove();vi.restoreAllMocks();vi.useRealTimers()
})
const mount=() => act(() => root!.render(<WebsiteUpdate/>))
const click=() => act(() => node.querySelector('button')!.click())
const advance=(ms:number) => act(() => vi.advanceTimersByTime(ms))

it('announces an available update only after notification', () => {
  vi.mocked(hasWebsiteUpdate).mockReturnValue(false);mount()
  expect(node.querySelector('section')).toBeNull()
  vi.mocked(hasWebsiteUpdate).mockReturnValue(true)
  act(() => window.dispatchEvent(new Event('xyz:website-update')))
  expect(node.querySelector('[role=status]')?.textContent).toContain('Website update ready')
})
it('acknowledges immediately, prevents repeated reloads, and allows retry if navigation stalls', () => {
  mount()
  act(() => {node.querySelector('button')!.click();node.querySelector('button')!.click()})
  expect(node.querySelector('button')?.disabled).toBe(true)
  expect(node.querySelector('button')?.getAttribute('aria-busy')).toBe('true')
  expect(node.textContent).toContain('Reloading…')
  expect(applyWebsiteUpdate).not.toHaveBeenCalled()
  advance(100)
  expect(applyWebsiteUpdate).toHaveBeenCalledOnce()
  click();advance(9900)
  expect(applyWebsiteUpdate).toHaveBeenCalledOnce()
  expect(node.querySelector('[role=alert]')?.textContent).toContain("Reload hasn't completed")
  expect(node.querySelector('button')?.disabled).toBe(false)
  click();advance(100)
  expect(applyWebsiteUpdate).toHaveBeenCalledTimes(2)
})
it('explains offline state and only reloads after the user retries online', () => {
  vi.spyOn(navigator,'onLine','get').mockReturnValue(false)
  mount();click();advance(10000)
  expect(applyWebsiteUpdate).not.toHaveBeenCalled()
  expect(node.querySelector('[role=alert]')?.textContent).toContain("You're offline")
  vi.spyOn(navigator,'onLine','get').mockReturnValue(true)
  click();advance(100)
  expect(applyWebsiteUpdate).toHaveBeenCalledOnce()
})
it('recovers from a synchronous navigation error without leaving the button disabled', () => {
  vi.mocked(applyWebsiteUpdate).mockImplementationOnce(() => {throw new Error('navigation blocked')})
  mount();click();advance(100)
  expect(node.querySelector('[role=alert]')?.textContent).toContain('Could not start the reload')
  expect(node.querySelector('button')?.disabled).toBe(false)
  click();advance(100)
  expect(applyWebsiteUpdate).toHaveBeenCalledTimes(2)
})
it('cancels deferred navigation and feedback timers on unmount', () => {
  mount();click();act(() => root!.unmount());root=undefined
  advance(15000)
  expect(applyWebsiteUpdate).not.toHaveBeenCalled()
})
