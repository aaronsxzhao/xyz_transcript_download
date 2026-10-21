// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import ReaderScreenshot from '../src/components/ReaderScreenshot'
import PlainNote from '../src/components/PlainNote'

let cleanup: (() => void) | undefined
afterEach(() => { cleanup?.(); cleanup=undefined; vi.useRealTimers() })

it('renders semantic Markdown and matching duplicate anchors without optional formatting', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'# 交易 **复盘**\n\n## 目录\n- [趋势](#趋势)\n\n---\n\n## 趋势\n\n**确认**后操作。\n\n- 观察\n  - 管理风险\n\n| 信号 | 行动 |\n| --- | --- |\n| 突破 | 等待 |\n\n## 趋势'}/>))
  expect(node.querySelector('h1')?.textContent).toBe('交易 复盘')
  expect(Array.from(node.querySelectorAll('h2'),h=>h.id)).toEqual(['趋势','趋势-1'])
  expect(node.querySelector('p strong')?.textContent).toBe('确认')
  expect(node.querySelector('li li')?.textContent).toContain('管理风险')
  expect(node.querySelector('table tbody td')?.textContent).toBe('突破')
  expect(node.textContent).not.toContain('目录')
})

it('keeps dangerous links and HTML inert while preserving readable labels', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'[unsafe](javascript:alert) [safe](https://example.com)\n\n<iframe src="https://example.com"></iframe>'}/>))
  expect(node.querySelectorAll('a')).toHaveLength(1)
  expect(node.querySelector('a')?.href).toBe('https://example.com/')
  expect(node.querySelector('iframe')).toBeNull()
  expect(node.textContent).toContain('unsafe')
})

it('keeps saved text readable and escapes HTML when formatting is unavailable', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'Saved note\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>'}/>))
  expect(node.textContent).toContain('Saved note')
  expect(node.textContent).toContain('<script>')
  expect(node.querySelector('script, img')).toBeNull()
})

it('loads private and HTTPS screenshots in fallback without allowing executable image URLs', () => {
  vi.useFakeTimers()
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'![private](/data/screenshots/a.png?signature=test)\n![remote](https://example.com/a.png)\n![unsafe](javascript:alert)\n![embedded](data:image/svg+xml,unsafe)'}/>))
  expect(node.querySelectorAll('img')).toHaveLength(0)
  act(()=>vi.advanceTimersByTime(250))
  expect(Array.from(node.querySelectorAll('img'), image=>image.getAttribute('src'))).toEqual(['/data/screenshots/a.png?signature=test&preview=true','https://example.com/a.png'])
  expect(node.textContent).toContain('unsafe')
})

it.each([403,404])('explains image HTTP %s instead of offering endless retries', async status => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status})))
  try {
    act(()=>root.render(<ReaderScreenshot src="/data/screenshots/private.png?signature=test" alt="chart"/>))
    await act(async()=>{node.querySelector('img')!.dispatchEvent(new Event('error')); await Promise.resolve()})
    await vi.waitFor(()=>expect(node.textContent).toContain(status===403?'Image link expired':'Source image is missing'))
    expect(node.textContent).not.toContain('Retry image')
  } finally { vi.unstubAllGlobals() }
})
