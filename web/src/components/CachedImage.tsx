import { useEffect, useState, type ReactNode } from 'react'
import { Image as ImageIcon } from 'lucide-react'
import { artworkUrl } from '../lib/artwork'

/** Reserve the image box and retain a visible fallback during slow/failed reads. */
type ImageProps = {src: string; alt?: string; className?: string; fallback?: ReactNode; fit?: 'cover'|'contain'; priority?: boolean}
export default function CachedImage(props: ImageProps) {
  return <ImageContent key={props.src} {...props} />
}
function ImageContent({src, alt='', className='', fallback, fit='cover', priority=false}: ImageProps) {
  const [state, setState] = useState<'loading'|'ready'|'failed'>('loading')
  const [retry, setRetry] = useState(0)
  const url = artworkUrl(src)
  useEffect(()=>{
    if(state!=='failed')return
    const online=()=>{setRetry(r=>r+1);setState('loading')}
    window.addEventListener('online',online)
    const timer=retry===0 ? setTimeout(online,3500) : undefined
    return ()=>{clearTimeout(timer);window.removeEventListener('online',online)}
  },[state,retry])
  return <div className={`cached-image ${className}`} role={alt ? 'img' : undefined} aria-label={alt || undefined} data-image-state={url ? state : 'empty'}>
    {state !== 'ready' && (fallback || <span className="cached-image-fallback" aria-hidden="true"><ImageIcon size={24}/></span>)}
    {url && state!=='failed' && <img src={url+(retry ? `&retry=${retry}` : '')} alt="" loading={priority ? "eager" : "lazy"} fetchPriority={priority ? "high" : "auto"} decoding="async" style={{objectFit:fit,opacity:state==='ready'?1:0}} onLoad={()=>setState('ready')} onError={()=>setState('failed')} />}
  </div>
}
