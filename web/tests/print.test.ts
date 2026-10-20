// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { printHtml } from '../src/lib/print'

const revoke = vi.fn()
beforeEach(() => {
  vi.useFakeTimers()
  const NativeURL = URL
  vi.stubGlobal('URL', class extends NativeURL {
    static createObjectURL = () => 'blob:http://localhost/print-preview'
    static revokeObjectURL = revoke
  })
})
afterEach(() => {
  document.body.replaceChildren()
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks()
})

it('reports a stalled print document and releases its private Blob URL', async () => {
  const pending = printHtml('<p>Notes with unavailable images</p>')
  const rejected = expect(pending).rejects.toThrow('Could not prepare the PDF')
  await vi.advanceTimersByTimeAsync(30000)
  await rejected
  expect(document.querySelector('iframe')).toBeNull()
  expect(revoke).toHaveBeenCalledWith('blob:http://localhost/print-preview')
})

it('reports a failed print document instead of leaving the action pending', async () => {
  const pending = printHtml('<p>Notes</p>')
  const rejected = expect(pending).rejects.toThrow('download Markdown')
  document.querySelector('iframe')!.dispatchEvent(new Event('error'))
  await rejected
  expect(document.querySelector('iframe')).toBeNull()
  expect(revoke).toHaveBeenCalledOnce()
})
