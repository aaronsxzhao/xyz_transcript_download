import { createElement, useMemo, type ReactNode } from 'react'
import { Lexer, type Token, type Tokens } from 'marked'
import ReaderScreenshot from './ReaderScreenshot'
import { uniqueNoteHeadingSlug, prepareNoteMarkdown, inlineNoteText, decodeNoteText as text } from '../lib/noteMarkdown'

export const hasImage=(items:Token[]):boolean=>items.some(t=>t.type==='image'||('tokens'in t&&Array.isArray(t.tokens)&&hasImage(t.tokens)))
const safeLink=(url:string)=>/^(https?:\/\/|mailto:|tel:|#|\/(?![\/\\]))/i.test(url)
const safeImage=(url:string)=>/^https?:\/\//i.test(url)||/^\/data\/(screenshots|thumbnails)\//.test(url)
/** Semantic Markdown is part of startup. No raw HTML or executable URLs. */
export default function ReadableMarkdown({markdown,imagesReady=true,omitToc=false,renderParagraph}:{markdown:string;imagesReady?:boolean;omitToc?:boolean;renderParagraph?:(paragraph:Tokens.Paragraph,key:number)=>ReactNode}) {
  const tokens=useMemo(()=>Lexer.lex(omitToc?prepareNoteMarkdown(markdown):markdown,{gfm:true}),[markdown,omitToc])
  const slugs:Record<string,number>=Object.create(null);let imageIndex=0
  const render=(items:Token[]):ReactNode[]=>items.map((token,index)=>{
    const key=index
    switch(token.type){
      case 'space':return null
      case 'heading':{const t=token as Tokens.Heading;return createElement(`h${t.depth}`,{key,id:uniqueNoteHeadingSlug(inlineNoteText(t.tokens),slugs)},render(t.tokens))}
      case 'paragraph':{const t=token as Tokens.Paragraph;return renderParagraph?.(t,key)??<p key={key}>{render(t.tokens)}</p>}
      case 'text':{const t=token as Tokens.Text;return <span key={key}>{t.tokens?render(t.tokens):text(t.text)}</span>}
      case 'escape':return <span key={key}>{text((token as Tokens.Escape).text)}</span>
      case 'strong':return <strong key={key}>{render((token as Tokens.Strong).tokens)}</strong>
      case 'em':return <em key={key}>{render((token as Tokens.Em).tokens)}</em>
      case 'del':return <del key={key}>{render((token as Tokens.Del).tokens)}</del>
      case 'codespan':return <code key={key}>{(token as Tokens.Codespan).text}</code>
      case 'code':return <pre key={key}><code>{(token as Tokens.Code).text}</code></pre>
      case 'br':return <br key={key}/>
      case 'hr':return <hr key={key}/>
      case 'blockquote':return <blockquote key={key}>{render((token as Tokens.Blockquote).tokens)}</blockquote>
      case 'html':return <span key={key}>{(token as Tokens.HTML).text}</span>
      case 'link':{const t=token as Tokens.Link;const children=render(t.tokens);const image=hasImage(t.tokens);const link=safeLink(t.href)?<a key={key} href={t.href} title={t.title||undefined} target={t.href.startsWith('#')?undefined:'_blank'} rel="noopener noreferrer" onClick={t.href.startsWith('#')?event=>{try{const target=document.getElementById(decodeURIComponent(t.href.slice(1)));if(target){event.preventDefault();target.scrollIntoView({block:'start'})}}catch{/* malformed anchor remains a normal link */}}:undefined}>{image?'Open linked source':children}</a>:null;return image?<span key={key}>{children}{link}</span>:link||<span key={key}>{children}</span>}
      case 'image':{const t=token as Tokens.Image;return safeImage(t.href)?<ReaderScreenshot key={key} src={t.href} alt={text(t.text)} ready={imagesReady} priority={imageIndex++<2}/>:<span key={key}>{text(t.text)}</span>}
      case 'list':{const t=token as Tokens.List;const children=t.items.map((item,i)=><li key={i}>{item.task&&<input type="checkbox" disabled checked={!!item.checked} aria-label="Task completed"/>}{render(item.tokens)}</li>);return t.ordered?<ol key={key} start={typeof t.start==='number'?t.start:1}>{children}</ol>:<ul key={key}>{children}</ul>}
      case 'table':{const t=token as Tokens.Table;return <div className="markdown-table" key={key} role="region" aria-label="Table" tabIndex={0}><table><thead><tr>{t.header.map((cell,i)=><th key={i} style={{textAlign:t.align[i]||undefined}}>{render(cell.tokens)}</th>)}</tr></thead><tbody>{t.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j} style={{textAlign:t.align[j]||undefined}}>{render(cell.tokens)}</td>)}</tr>)}</tbody></table></div>}
      default:return <span key={key}>{'text'in token?text(String(token.text)):''}</span>
    }
  })
  return <>{render(tokens)}</>
}
