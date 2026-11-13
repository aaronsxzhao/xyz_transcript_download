import {Lexer, type Tokens} from 'marked'
import {inlineNoteText} from './noteMarkdown'

/** Group an X source entry with its adjacent bare Article/share link without
 * asserting equivalent destinations or removing either citation.
 */
function xSourcePair(source:string, related:string):boolean {
  try {
    const a=new URL(source),b=new URL(related)
    if([a,b].some(u=>u.protocol!=='https:'||u.username||u.password||u.port||u.search||u.hash))return false
    const x=(u:URL)=>['x.com','twitter.com','www.x.com','www.twitter.com'].includes(u.hostname)
    return x(a)&&/^\/(?:i|[\w]+)\/status\/\d+\/?$/.test(a.pathname)
      && (b.hostname==='t.co'&&/^\/[A-Za-z0-9]+$/.test(b.pathname)||x(b)&&/^\/i\/article\/\d+\/?$/.test(b.pathname))
  } catch {return false}
}

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
    const pair=link&&previous&&label===link.href&&previousLabel==='Original source'&&xSourcePair(previous.href,link.href)
    previous=link
    if(pair){
      output+=markdown.slice(kept,start).trimEnd()+' · [Linked source](<'+link.href+'>)'+newline+newline
      kept=cursor;removed=true;previous=null
    } else if(duplicate){output+=markdown.slice(kept,start);kept=cursor;removed=true}
  }
  return output+markdown.slice(kept)
}
