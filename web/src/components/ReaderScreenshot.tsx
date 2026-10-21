import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { recordReaderImage } from '../lib/pageTiming'
import { reloadFreshPage } from '../lib/chunkRecovery'
import { useDialog } from '../lib/reading'

/** Bounded preview; full-resolution viewing is an explicit action. */
export default function ReaderScreenshot({src,alt='',ready=true,priority=false}:{src:string;alt?:string;ready?:boolean;priority?:boolean}) {
  const imageStarted = useRef(performance.now())
  const [open,setOpen]=useState(false)
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
  useDialog(open,()=>setOpen(false))
  if(failed) return <span role="status" className="block my-4 rounded-lg border border-dark-border p-4 text-sm text-gray-400"><span className="block">{alt || 'Screenshot'} — {checking ? 'Checking image…' : reason === 'missing' ? 'Source image is missing. Recover it from the original video or a backup.' : reason === 'expired' ? 'Image link expired. Refresh this page to renew it.' : 'Could not download image.'}</span>{reason === 'missing' && document.querySelector('[data-screenshot-recovery]') && <button className="underline mt-2" onClick={() => { const details = document.querySelector<HTMLDetailsElement>('[data-screenshot-recovery]'); if (details) { details.open = true; details.scrollIntoView({block:'center'}); details.querySelector('summary')?.focus() } }}>Open screenshot recovery</button>}{reason === 'expired' ? <button className="underline mt-2" onClick={reloadFreshPage}>Refresh image links</button> : reason !== 'missing' && <button disabled={checking} className="underline mt-2" onClick={()=>setFailed(false)}>Retry image</button>}</span>
  return <><button type="button" className="reader-screenshot" aria-label={`Enlarge ${alt || 'screenshot'}`} onClick={()=>ready&&setOpen(true)}>
    {ready ? <img src={preview} alt={alt || 'Screenshot'} loading={priority?'eager':'lazy'} decoding="async" referrerPolicy="no-referrer" onLoad={()=>{if(priority) recordReaderImage(performance.now()-imageStarted.current)}} onError={()=>setFailed(true)}/> : <span className="text-sm text-gray-400">Loading screenshot…</span>}
  </button>{open&&createPortal(<div role="dialog" aria-modal="true" aria-label="Enlarged screenshot" className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={()=>setOpen(false)}><button className="absolute top-4 right-4 bg-dark-surface text-white rounded-lg px-3 py-2" aria-label="Close enlarged screenshot" onClick={()=>setOpen(false)}>Close</button><img src={src} alt={alt || 'Screenshot'} className="max-w-[95vw] max-h-[90dvh] object-contain"/></div>,document.body)}</>
}
