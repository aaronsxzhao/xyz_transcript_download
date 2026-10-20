import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useDialog } from '../lib/reading'

/** Bounded preview; full-resolution viewing is an explicit action. */
export default function ReaderScreenshot({src,alt='',ready=true,priority=false}:{src:string;alt?:string;ready?:boolean;priority?:boolean}) {
  const [open,setOpen]=useState(false)
  const [failed,setFailed]=useState(false)
  useDialog(open,()=>setOpen(false))
  if(failed) return <span className="block my-4 text-sm text-gray-400">{alt || 'Screenshot'} — unavailable <button className="underline" onClick={()=>setFailed(false)}>Retry image</button></span>
  return <><button type="button" className="reader-screenshot" aria-label={`Enlarge ${alt || 'screenshot'}`} onClick={()=>ready&&setOpen(true)}>
    {ready ? <img src={src} alt={alt || 'Screenshot'} loading={priority?'eager':'lazy'} decoding="async" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/> : <span className="text-sm text-gray-400">Loading screenshot…</span>}
  </button>{open&&createPortal(<div role="dialog" aria-modal="true" aria-label="Enlarged screenshot" className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={()=>setOpen(false)}><button className="absolute top-4 right-4 bg-dark-surface text-white rounded-lg px-3 py-2" aria-label="Close enlarged screenshot" onClick={()=>setOpen(false)}>Close</button><img src={src} alt={alt || 'Screenshot'} className="max-w-[95vw] max-h-[90dvh] object-contain"/></div>,document.body)}</>
}
