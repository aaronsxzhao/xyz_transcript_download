import {lazy, useState, useEffect, useRef} from 'react'
import {OptionalTool} from './DeferredView'
import {createPortal} from 'react-dom'
import {useDialog} from '../lib/reading'
import { recordReaderImage } from '../lib/pageTiming'
import { reloadFreshPage } from '../lib/chunkRecovery'
const loadGallery=()=>import('./ScreenshotGallery')
const ScreenshotGallery=lazy(loadGallery)
function GalleryPending({onClose,src,failed=false}:{onClose:()=>void;src?:string;failed?:boolean}) {
  useDialog(true,onClose)
  return createPortal(<div role="dialog" aria-modal="true" aria-label="Enlarged screenshot" className="ui-scope fixed inset-0 z-50 bg-black/95 flex flex-col items-center justify-center gap-4"><p role="status">{failed?'Image controls unavailable. Original image:':'Loading image controls…'}</p>{src&&<img src={src} alt="Original screenshot" style={{maxWidth:'100%',maxHeight:'75dvh',objectFit:'contain'}}/>}<button onClick={onClose}>Close</button></div>,document.body)
}

/** Bounded preview; full-resolution viewing is an explicit action. */
export default function ReaderScreenshot({src,alt='',ready=true,priority=false}:{src:string;alt?:string;ready?:boolean;priority?:boolean}) {
  const imageStarted = useRef(performance.now())
  const [open,setOpen]=useState(false)
  const [gallery,setGallery]=useState<{src:string;alt:string}[]>([])
  const [selected,setSelected]=useState(0)
  const [failed,setFailed]=useState(false)
  const [reason, setReason] = useState('')
  const [checking, setChecking] = useState(false)
  const preview = src.startsWith('/data/') ? `${src}${src.includes('?') ? '&' : '?'}preview=true` : src
  useEffect(() => { setFailed(false); setReason(''); setOpen(false) }, [src])
  useEffect(() => {
    if (!failed || !src.startsWith('/data/')) return
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 5000)
    setChecking(true)
    fetch(preview, {signal:controller.signal}).then(r => {
      if (!controller.signal.aborted) setReason(r.status === 404 ? 'missing' : r.status === 403 ? 'expired' : 'network')
    }).catch(() => { if (!controller.signal.aborted) setReason('network') }).finally(() => { clearTimeout(timer); setChecking(false) })
    return () => { clearTimeout(timer); controller.abort() }
  }, [failed, src])
  if(failed) return <span role="status" className="block my-4 rounded-lg border border-dark-border p-4 text-sm text-gray-400"><span className="block">{alt || 'Screenshot'} — {checking ? 'Checking image…' : reason === 'missing' ? 'Source image is missing. Recover it from the original video or a backup.' : reason === 'expired' ? 'Image link expired. Refresh this page to renew it.' : 'Could not download image.'}</span>{reason === 'missing' && document.querySelector('[data-screenshot-recovery]') && <button className="underline mt-2" onClick={() => { const details = document.querySelector<HTMLDetailsElement>('[data-screenshot-recovery]'); if (details) { details.open = true; details.scrollIntoView({block:'center'}); details.querySelector('summary')?.focus() } }}>Open screenshot recovery</button>}{reason === 'expired' ? <button className="underline mt-2" onClick={reloadFreshPage}>Refresh image links</button> : reason !== 'missing' && <button disabled={checking} className="underline mt-2" onClick={()=>setFailed(false)}>Retry image</button>}</span>
  return <><span className="screenshot-block"><button type="button" className="reader-screenshot" aria-label={`Enlarge ${alt || 'screenshot'}`} data-original-src={src} data-caption={alt} onClick={event=>{if(!ready)return;const buttons=Array.from((event.currentTarget.closest('main')||document).querySelectorAll<HTMLButtonElement>('button.reader-screenshot'));setGallery(buttons.map(button=>({src:button.dataset.originalSrc!,alt:button.dataset.caption||''})));setSelected(Math.max(0,buttons.indexOf(event.currentTarget)));setOpen(true)}}>
    {ready ? <img src={preview} alt={alt || 'Screenshot'} loading={priority?'eager':'lazy'} decoding="async" referrerPolicy="no-referrer" onLoad={()=>{if(priority) recordReaderImage(performance.now()-imageStarted.current,preview)}} onError={()=>setFailed(true)}/> : <span className="text-sm text-gray-400">Loading screenshot…</span>}
  </button>{alt && <span className="screenshot-caption">{alt}</span>}</span>{open&&<OptionalTool fallback={<GalleryPending onClose={()=>setOpen(false)}/>} errorFallback={<GalleryPending failed src={src} onClose={()=>setOpen(false)}/>}><ScreenshotGallery images={gallery} initial={selected} onClose={()=>setOpen(false)}/></OptionalTool>}</>
}
