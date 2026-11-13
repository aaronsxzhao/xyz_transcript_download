import {describe,it,expect} from 'vitest'
import {articleDisplayMarkdown} from '../src/lib/articleLinks'
describe('generated source duplication',()=>{
 it('collapses only the adjacent bare repetition',()=>{
  const s='[Original source](https://x.com/i/article/123)\n\nhttps://x.com/i/article/123\n\nBody'
  expect(articleDisplayMarkdown(s)).toBe('[Original source](https://x.com/i/article/123)\n\nBody')
 })
 it('retains distinct citations, code, separated references and Markdown definitions',()=>{
  for(const body of ['[Different evidence](https://x.com/a)','```\nhttps://x.com/a\n```','A paragraph\n\nhttps://x.com/a','[citation][c]\n\n[c]: https://x.com/a']){
   const s='[Original source](https://x.com/a)\n\n'+body
   expect(articleDisplayMarkdown(s)).toBe(s)
  }
 })
})

it('groups X post and adjacent Article short link but retains both destinations and later citations',()=>{
 const post='https://x.com/i/status/2091515787366306154',short='https://t.co/5w8ILIIelz'
 const source=`[Original source](${post})\n\n${short}\n\nBody\n\nhttps://t.me/example`
 const actual=articleDisplayMarkdown(source)
 expect(actual).toBe(`[Original source](${post}) · [Linked source](<${short}>)\n\nBody\n\nhttps://t.me/example`)
 expect(articleDisplayMarkdown(actual)).toBe(actual)
})

it('does not group a prose citation, unrelated host, code, or nonadjacent short link',()=>{
 for(const middle of ['A source: https://t.co/abc','https://example.com/article','```\nhttps://t.co/abc\n```','Body\n\nhttps://t.co/abc']) {
  const source='[Original source](https://x.com/i/status/123)\n\n'+middle
  expect(articleDisplayMarkdown(source)).toBe(source)
 }
})
