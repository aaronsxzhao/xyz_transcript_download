// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import SummaryExport from '../src/pages/SummaryExport'
import { openSummaryExport } from '../src/lib/summaryExport'
import { clearTokens } from '../src/lib/auth'
let root: ReturnType<typeof createRoot> | undefined
let node: HTMLDivElement
async function mount() {
  node=document.createElement('div'); document.body.append(node); root=createRoot(node)
  await act(async()=>root!.render(<MemoryRouter initialEntries={['/exports/summaries/one']}><Routes><Route path="/exports/summaries/:eid" element={<SummaryExport/>}/></Routes></MemoryRouter>))
}
afterEach(()=>{if(root)act(()=>root!.unmount());root=undefined;node?.remove();clearTokens();vi.restoreAllMocks();vi.unstubAllGlobals()})
it('opens only a content identifier and severs the opener before navigating',()=>{
  const tab={opener:window,location:{replace:vi.fn(()=>expect(tab.opener).toBeNull())}}
  vi.spyOn(window,'open').mockReturnValue(tab as unknown as Window)
  expect(openSummaryExport('private/id')).toBe(true)
  expect(tab.location.replace).toHaveBeenCalledWith('/exports/summaries/private%2Fid')
  vi.mocked(window.open).mockReturnValue(null)
  expect(openSummaryExport('one')).toBe(false)
})
it('loads using a header and renders script-disabled HTML without a token URL',async()=>{
  sessionStorage.setItem('xyz_access_token','synthetic-session')
  const fetch=vi.fn().mockResolvedValue(new Response('<h1>Export</h1>',{headers:{'Content-Type':'text/html'}}));vi.stubGlobal('fetch',fetch)
  await mount()
  expect(fetch.mock.calls[0][0]).toBe('/api/summaries/one/html')
  expect(new Headers(fetch.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer synthetic-session')
  const frame=node.querySelector('iframe')!
  expect(frame.getAttribute('sandbox')).toBe('')
  expect(frame.getAttribute('srcdoc')).toContain('<h1>Export</h1>')
})
it('shows a recoverable export error and never renders the error document',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(new Response('<h1>proxy failure</h1>',{status:524})).mockResolvedValueOnce(new Response('<p>Recovered</p>',{headers:{'Content-Type':'text/html'}}));vi.stubGlobal('fetch',fetch)
  await mount();expect(node.textContent).toContain('HTTP 524');expect(node.querySelector('iframe')).toBeNull()
  await act(async()=>node.querySelector('button')!.click())
  expect(node.querySelector('iframe')!.getAttribute('srcdoc')).toContain('Recovered')
})
