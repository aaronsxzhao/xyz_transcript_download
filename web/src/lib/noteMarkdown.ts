import { Lexer, walkTokens, type Tokens } from 'marked'

/** Repair duplicated ATX markers only in parsed, top-level numbered headings. */
export function normalizeNoteHeadings(markdown: string): string {
  const duplicate = /^( {0,3}#{1,6}[\t ]+\d+(?:[.．]\d+)*(?:[.．、])?[\t ]+)#{1,6}[\t ]+(?=\S)/m
  if (!duplicate.test(markdown)) return markdown
  // Lexer normalizes newlines. Edit original heading lines so code examples
  // and reference definitions retain their exact bytes, including CRLF.
  const lines = markdown.split(/(\r\n|\n|\r)/)
  let line = 0
  for (const token of Lexer.lex(markdown)) {
    if (token.type === 'heading') lines[line * 2] = lines[line * 2].replace(duplicate, '$1')
    line += (token.raw.match(/\n/g) || []).length
  }
  return lines.join('')
}

export function prepareNoteMarkdown(markdown: string) {
  markdown = normalizeNoteHeadings(markdown)
  const tokens = Lexer.lex(markdown)
  const index = tokens.findIndex(token => token.type === 'heading' && token.depth === 2 && /^(目录|Table of Contents)$/i.test(token.text.trim()))
  if (index < 0) return markdown
  let end = index + 1
  while (end < tokens.length && tokens[end].type !== 'heading') end++
  const body = tokens.slice(index + 1, end)
  // Remove only a generated navigation list, never prose or fenced source.
  if (!body.some(token => token.type === 'list') || body.some(token => !['list', 'space', 'hr'].includes(token.type))) return markdown
  return [...tokens.slice(0, index), ...tokens.slice(end)].map(token => token.raw).join('')
}

export function noteHeadingSlug(text: string) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}_\s-]/gu, '').trim().replace(/\s+/g, '-').replace(/-+/g, '-')
}

export function uniqueNoteHeadingSlug(text: string, counts: Record<string, number>): string {
  const base = noteHeadingSlug(text) || 'section'
  let slug = base
  while (counts[slug] !== undefined) {
    counts[base] = (counts[base] || 0) + 1
    slug = `${base}-${counts[base]}`
  }
  counts[slug] = 0
  return slug
}

export function decodeNoteText(value: string): string {
  return value.replace(/&(?:amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-f]+);/gi, entity => {
    const named: Record<string, string> = {'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&apos;':"'",'&nbsp;':'\u00a0'}
    if (named[entity.toLowerCase()]) return named[entity.toLowerCase()]
    const hex = entity.toLowerCase().startsWith('&#x')
    const code = parseInt(entity.slice(hex ? 3 : 2, -1), hex ? 16 : 10)
    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : entity
  })
}

type Inline = {type:string;text?:string;tokens?:Inline[]}
export function inlineNoteText(tokens:Inline[]):string {
  return tokens.map(token=>token.tokens?inlineNoteText(token.tokens):token.type === 'codespan' ? token.text || '' : decodeNoteText(token.text || '')).join('')
}

export function extractNoteToc(markdown:string,preserveSource=false) {
  const counts:Record<string,number>=Object.create(null)
  const headings:{level:number;text:string;slug:string}[]=[]
  walkTokens(Lexer.lex(preserveSource?markdown:prepareNoteMarkdown(markdown)),token=>{
    if(token.type!=='heading')return
    const heading=token as Tokens.Heading
    const text=inlineNoteText(heading.tokens)
    const slug=uniqueNoteHeadingSlug(text,counts)
    if(heading.depth<=3)headings.push({level:heading.depth,text,slug})
  })
  return headings
}
