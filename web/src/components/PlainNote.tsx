import { useEffect, useState } from 'react'

/** Built-in readable note, including screenshots, while rich formatting loads. */
export default function PlainNote({markdown}:{markdown:string}) {
  const [imagesReady, setImagesReady] = useState(false)
  useEffect(()=>{ const timer=setTimeout(()=>setImagesReady(true),250);return ()=>clearTimeout(timer) },[])
  const image = /!\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g
  const parts = []; let from = 0; let count = 0
  for (const match of markdown.matchAll(image)) {
    parts.push(<span key={`text-${from}`} className="whitespace-pre-wrap">{markdown.slice(from,match.index)}</span>)
    const source = match[2]
    if (imagesReady && (/^https?:\/\//i.test(source) || /^\/data\/(screenshots|thumbnails)\//.test(source))) {
      parts.push(<img key={`image-${match.index}`} src={source} alt={match[1] || 'Screenshot'} loading={count++<2 ? 'eager':'lazy'} decoding="async" className="block w-full h-auto rounded-lg my-4" />)
    } else parts.push(<span key={`image-${match.index}`}>{match[1]}</span>)
    from = match.index! + match[0].length
  }
  parts.push(<span key={`text-${from}`} className="whitespace-pre-wrap">{markdown.slice(from)}</span>)
  return <article data-rendering="plain" aria-label="Readable note" className="break-words text-gray-200 leading-relaxed">{parts}</article>
}
