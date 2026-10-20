// @vitest-environment jsdom
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import PlainNote from '../src/components/PlainNote'

let cleanup: (() => void) | undefined
afterEach(() => { cleanup?.(); cleanup=undefined; vi.useRealTimers() })

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
  expect(Array.from(node.querySelectorAll('img'), image=>image.getAttribute('src'))).toEqual(['/data/screenshots/a.png?signature=test','https://example.com/a.png'])
  expect(node.textContent).toContain('unsafe')
})
