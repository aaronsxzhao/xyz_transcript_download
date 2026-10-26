// @vitest-environment jsdom
import { expect, it } from 'vitest'
import { escapeHtml, markdownToSafeHtml } from '../src/lib/safeHtml'
import {buildNotionExportMarkdown} from '../src/lib/notionExport'
import type {VideoTask} from '../src/lib/api'

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

it.each(['\n','\r\n'])('exports one title while preserving the complete saved body with %j newlines',newline=>{
 const body=['## Original chapter','','All conditions remain.','','> Exact original quotation.','','![Evidence](/data/screenshots/note.jpg)'].join(newline)
 const task={title:'Source [title]',platform:'youtube',duration:65,style:'detailed',url:'https://example.com/source'} as VideoTask
 const result=buildNotionExportMarkdown(task,'# Source [title]'+newline+newline+body)
 expect(result.match(/^# Source \[title\]$/gm)).toHaveLength(1)
 expect(result).toContain(body)
 expect(result).toContain('- Duration: 1:05')
})
it('retains a source heading that differs from the task title',()=>{
 const task={title:'Imported title',duration:0} as VideoTask
 expect(buildNotionExportMarkdown(task,'# Original publication heading\n\nComplete source.')).toContain('# Original publication heading\n\nComplete source.')
})
it.each([true,false])('preserves an opening indented code block in Notion export (title=%s)',async title=>{
 const task={title:'Source',duration:0} as VideoTask
 const code='    first()\n    second()'
 const markdown=buildNotionExportMarkdown(task,(title?'# Source\n\n':'')+code+'\n\nFollowing explanation.')
 expect(markdown).toContain(code)
 const html=await markdownToSafeHtml(markdown)
 expect(html).toContain('<pre><code>first()\nsecond()')
})
