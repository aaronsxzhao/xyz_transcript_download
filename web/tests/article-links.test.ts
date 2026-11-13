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
