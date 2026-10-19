// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { escapeHtml, markdownToSafeHtml } from '../src/lib/safeHtml'

it('removes executable content from copied and printed Markdown', async () => {
  const html = await markdownToSafeHtml('# Notes\n\n<script>window.compromised=1</script><img src="x" onerror="window.compromised=1"><a href="javascript:alert(1)">link</a>')
  expect(html).not.toContain('<script')
  expect(html).not.toContain('onerror')
  expect(html).not.toContain('javascript:')
  expect(html).toContain('<h1>Notes</h1>')
})

it('preserves ordinary formatting and signed image links', async () => {
  const html = await markdownToSafeHtml('**Useful**\n\n![Evidence](/data/screenshots/task_00-01.jpg?expires=123&signature=abc)')
  expect(html).toContain('<strong>Useful</strong>')
  expect(html).toContain('signature=abc')
})

it('escapes titles embedded in print documents', () => {
  expect(escapeHtml('</title><script>bad()</script>')).toBe('&lt;/title&gt;&lt;script&gt;bad()&lt;/script&gt;')
})
