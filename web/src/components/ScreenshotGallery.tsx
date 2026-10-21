import {useEffect, useState} from 'react'
import {createPortal} from 'react-dom'
import {useDialog} from '../lib/reading'

export default function ScreenshotGallery({images,initial,onClose}:{images:{src:string;alt:string}[];initial:number;onClose:()=>void}) {
  const [index,setIndex]=useState(initial)
  const [zoom,setZoom]=useState(1)
  const [state,setState]=useState<'loading'|'ready'|'error'>('loading')
  const [retry,setRetry]=useState(0)
  const current=images[index]
  useDialog(true,onClose)
  useEffect(()=>{setZoom(1);setState('loading')},[index])
  useEffect(()=>{
    const handle=(event:KeyboardEvent)=>{
      if(event.key==='ArrowLeft'){event.preventDefault();setIndex(i=>Math.max(0,i-1))}
      if(event.key==='ArrowRight'){event.preventDefault();setIndex(i=>Math.min(images.length-1,i+1))}
    }
    window.addEventListener('keydown',handle)
    return()=>window.removeEventListener('keydown',handle)
  },[images.length])
  return createPortal(<div role="dialog" aria-modal="true" aria-label="Enlarged screenshot" className="fixed inset-0 z-50 bg-black/95 flex flex-col p-4" onClick={onClose}>
    <div className="flex items-center justify-center gap-3 flex-wrap shrink-0 pb-3" onClick={e=>e.stopPropagation()}>
      <button disabled={index===0} onClick={()=>setIndex(index-1)}>Previous</button>
      <span aria-live="polite">{index+1} / {images.length}</span>
      <button disabled={index===images.length-1} onClick={()=>setIndex(index+1)}>Next</button>
      <button aria-label="Zoom out" disabled={zoom<=1} onClick={()=>setZoom(z=>Math.max(1,z-.5))}>−</button>
      <button onClick={()=>setZoom(1)}>Fit · {Math.round(zoom*100)}%</button>
      <button aria-label="Zoom in" disabled={zoom>=4} onClick={()=>setZoom(z=>Math.min(4,z+.5))}>+</button>
      <button aria-label="Close enlarged screenshot" onClick={onClose}>Close</button>
    </div>
    <div className="flex-1 min-h-0 overflow-auto" onClick={e=>e.stopPropagation()}>
      {state==='loading'&&<p role="status" className="text-center p-4">Loading original image…</p>}
      {state==='error'?<div role="alert" className="text-center p-4">Original image could not load. <button onClick={()=>{setState('loading');setRetry(n=>n+1)}}>Retry original</button></div>:
      <img key={`${index}:${retry}`} src={current.src} alt={current.alt||'Screenshot'} referrerPolicy="no-referrer" onLoad={()=>setState('ready')} onError={()=>setState('error')} style={{display:state==='ready'?'block':'none',width:zoom===1?'auto':`${zoom*100}%`,maxWidth:zoom===1?'100%':'none',maxHeight:zoom===1?'calc(100dvh - 120px)':'none',margin:'0 auto',objectFit:'contain'}}/>}
    </div>
    <p className="text-center text-sm text-gray-400 pt-2 shrink-0">{current.alt}</p>
  </div>,document.body)
}
