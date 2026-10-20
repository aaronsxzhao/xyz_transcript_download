import { Lexer, type Tokens } from 'marked'

export function prepareNoteMarkdown(markdown: string) {
  return markdown.replace(/^##\s*(?:目录|Table of Contents)\s*\n[\s\S]*?(?=\n---\n|\n## )/im, '').replace(/^\n---\n/m, '\n')
}

export function noteHeadingSlug(text: string) {
  return text.toLowerCase().replace(/[^\w\u4e00-\u9fff\s-]/g, '').trim().replace(/\s+/g, '-').replace(/-+/g, '-')
}

type Inline = {type:string;text?:string;tokens?:Inline[]}
export function inlineNoteText(tokens:Inline[]):string {
  return tokens.map(token=>token.tokens?inlineNoteText(token.tokens):token.text||'').join('')
}

export function extractNoteToc(markdown:string) {
  const counts:Record<string,number>=Object.create(null)
  return Lexer.lex(prepareNoteMarkdown(markdown)).filter(token=>token.type==='heading').map(token=>{
    const heading=token as Tokens.Heading
    const text=inlineNoteText(heading.tokens)
    const base=noteHeadingSlug(text);const n=counts[base]||0;counts[base]=n+1
    return {level:heading.depth,text,slug:base+(n?`-${n}`:'')}
  }).filter(heading=>heading.level<=3)
}

type Node = {tagName?:string;value?:string;properties?:Record<string,unknown>;children?:Node[]}
/** Match Contents anchors in both the built-in reader and rich rendering. */
export function rehypeNoteHeadings() {
  return (tree:Node)=>{
    const counts:Record<string,number>=Object.create(null)
    const content=(node:Node):string=>node.value||node.children?.map(content).join('')||''
    const visit=(node:Node)=>{
      if(node.tagName&&/^h[1-6]$/.test(node.tagName)){
        const base=noteHeadingSlug(content(node));const n=counts[base]||0;counts[base]=n+1
        node.properties={...node.properties,id:base+(n?`-${n}`:'')}
      }
      node.children?.forEach(visit)
    }
    visit(tree)
  }
}
