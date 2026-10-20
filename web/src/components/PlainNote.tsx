import { useEffect, useState } from 'react'
import ReadableMarkdown from './ReadableMarkdown'

/** Fully formatted note even when optional rich enhancements cannot load. */
export default function PlainNote({markdown}:{markdown:string}) {
  const [imagesReady,setImagesReady]=useState(false)
  useEffect(()=>{const timer=setTimeout(()=>setImagesReady(true),250);return()=>clearTimeout(timer)},[])
  return <article data-rendering="plain" aria-label="Readable note" className="note-prose prose prose-invert max-w-none"><ReadableMarkdown markdown={markdown} imagesReady={imagesReady} omitToc/></article>
}
