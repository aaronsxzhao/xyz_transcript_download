import {useEffect, useState} from 'react'
import ReadableMarkdown, {hasImage} from './ReadableMarkdown'
import {inlineNoteText} from '../lib/noteMarkdown'
import './ArticleNote.css'

export function articleEmbed(href:string):{src:string;name:string;audio?:boolean}|null {
  try {
    const url=new URL(href)
    if(url.protocol!=='https:'||url.username||url.password||url.port)return null
    const host=url.hostname.replace(/^www\./,'')
    const video=host==='youtu.be'?url.pathname.slice(1):['youtube.com','m.youtube.com','youtube-nocookie.com'].includes(host)?url.searchParams.get('v')||url.pathname.match(/^\/(?:embed|shorts|live)\/([^/]+)\/?$/)?.[1]:''
    if(video&&/^[\w-]{11}$/.test(video)){
      const value=url.searchParams.get('start')||url.searchParams.get('t')||url.hash.match(/^#t=(.+)$/)?.[1]||''
      const clock=value.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/)
      const seconds=/^\d+$/.test(value)?Number(value):clock?Number(clock[1]||0)*3600+Number(clock[2]||0)*60+Number(clock[3]||0):0
      const start=Number.isSafeInteger(seconds)&&seconds>0&&seconds<=604800?`?start=${seconds}`:''
      return {src:`https://www.youtube-nocookie.com/embed/${video}${start}`,name:'YouTube'}
    }
    const bili=host==='bilibili.com'?url.pathname.match(/^\/video\/(BV[\w]{10})\/?$/)?.[1]:null
    if(bili){const page=url.searchParams.get('p')||'';return {src:`https://player.bilibili.com/player.html?bvid=${bili}&autoplay=0${/^[1-9]\d{0,3}$/.test(page)?`&p=${page}`:''}`,name:'Bilibili'}}
    const spotify=host==='open.spotify.com'?url.pathname.match(/^\/(?:embed\/)?(episode|track|album|show)\/([a-zA-Z0-9]{22})\/?$/):null
    if(spotify)return {src:`https://open.spotify.com/embed/${spotify[1]}/${spotify[2]}`,name:'Spotify',audio:true}
  } catch { /* Malformed destinations remain ordinary links. */ }
  return null
}

function ArticleLink({href,label}:{href:string;label:string}) {
  const [loaded,setLoaded]=useState(false)
  const [pending,setPending]=useState(false)
  const [slow,setSlow]=useState(false)
  const embed=articleEmbed(href)
  let host='',path=''
  try {const url=new URL(href);host=url.hostname;path=decodeURIComponent(url.pathname).replace(/[-_]/g,' ').slice(0,100)} catch { /* Keep original label. */ }
  const title=label===href||!label?path&&path!=='/'?path:host:label
  useEffect(()=>{setLoaded(false);setPending(false);setSlow(false)},[href])
  useEffect(()=>{if(!pending)return;const timer=setTimeout(()=>setSlow(true),12000);return()=>clearTimeout(timer)},[pending])
  return <section className="article-link-card" aria-label={`${embed?.name||'Linked source'}: ${title}`}>
    <a className="article-link-target" href={href} target="_blank" rel="noopener noreferrer">
      <span className="article-link-host">{embed?.name||host}</span>
      <strong>{title}</strong><span className="article-link-action">Open original ↗</span>
    </a>
    {embed&&!loaded&&<button type="button" className="article-embed-button" onClick={()=>{setLoaded(true);setPending(true)}}>Load {embed.name} player</button>}
    {embed&&loaded&&<>
      {pending&&<p role="status">{slow?'Player is taking longer to load. You can open the original above.':'Loading player…'}</p>}
      <iframe className={embed.audio?'article-audio-embed':'article-video-embed'} src={embed.src} title={`${embed.name}: ${title}`} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-presentation allow-popups" allow="encrypted-media; fullscreen; picture-in-picture" allowFullScreen onLoad={()=>setPending(false)}/>
      <button type="button" className="article-embed-button" onClick={()=>{setLoaded(false);setPending(false);setSlow(false)}}>Close player</button>
    </>}
  </section>
}

/** Keep original prose and inline citations; enhance only standalone links. */
export default function ArticleNote({markdown}:{markdown:string}) {
  return <article data-rendering="plain" aria-label="Readable note" className="note-prose prose prose-invert max-w-none"><ReadableMarkdown markdown={markdown} renderParagraph={(paragraph,index)=>{const link=paragraph.tokens.length===1?paragraph.tokens[0]:null;return link?.type==='link'&&link.tokens&&/^https?:\/\//i.test(link.href)&&!hasImage(link.tokens)?<ArticleLink key={index+link.href} href={link.href} label={inlineNoteText(link.tokens)}/>:null}}/></article>
}
