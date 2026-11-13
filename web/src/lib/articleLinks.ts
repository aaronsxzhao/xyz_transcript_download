import {Lexer, type Tokens} from 'marked'
import {inlineNoteText} from './noteMarkdown'

/** Only collapse an adjacent bare URL duplicated by the generated source link.
 * Preserve citations, differently labelled links, code and saved Markdown.
 */
export function articleDisplayMarkdown(markdown:string):string {
  const tokens=Lexer.lex(markdown)
  let previous:Tokens.Link | null=null
  let cursor=0, kept=0, output='', removed=false
  const newline=markdown.includes('\r\n')?'\r\n':'\n'
  for(const token of tokens){
    const raw=token.raw.replace(/\n/g,newline)
    const start=markdown.indexOf(raw,cursor)
    if(start<0)return markdown
    if(markdown.slice(cursor,start).trim())previous=null
    cursor=start+raw.length
    if(token.type==='space'){if(removed)kept=cursor;continue}
    removed=false
    const link=token.type==='paragraph'&&token.tokens?.length===1&&token.tokens[0].type==='link'
      ? token.tokens[0] as Tokens.Link : null
    const label=link?inlineNoteText(link.tokens):''
    const previousLabel=previous?inlineNoteText(previous.tokens):''
    const duplicate=link&&previous&&link.href===previous.href&&label===link.href&&previousLabel==='Original source'
    previous=link
    if(duplicate){output+=markdown.slice(kept,start);kept=cursor;removed=true}
  }
  return output+markdown.slice(kept)
}
