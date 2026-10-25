import {useEffect, useRef, useState} from 'react'
import {createPortal} from 'react-dom'
import {useDialog} from '../lib/reading'

export default function ScreenshotGallery({images,initial,onClose}:{images:{src:string;alt:string}[];initial:number;onClose:()=>void}) {
  type LoadState='loading'|'ready'|'error'|'timeout'
  const [view,setView]=useState({index:initial,zoom:1,state:'loading' as LoadState,retry:0})
  const {index,zoom,state,retry}=view
  const viewport=useRef<HTMLDivElement>(null)
  const pointers=useRef(new Map<number,{x:number;y:number}>())
  const gesture=useRef({distance:0,zoom:1})
  const current=images[index]
  const setZoom=(value:number|((value:number)=>number))=>setView(v=>({...v,zoom:typeof value==='function'?value(v.zoom):value}))
  const setState=(state:LoadState)=>setView(v=>v.index===index&&v.retry===retry?{...v,state}:v)
  const setIndex=(value:number|((value:number)=>number))=>{
    // Selection and its loading/fit state must change in the same commit.
    // A cached image can finish before a later passive reset effect runs.
    setView(v=>{const next=typeof value==='function'?value(v.index):value;return next===v.index?v:{index:next,zoom:1,state:'loading',retry:0}})
    pointers.current.clear()
    viewport.current?.scrollTo(0,0)
  }
  useDialog(true,onClose)
  useEffect(()=>{
    if(state!=='loading') return
    const timer=setTimeout(()=>setState('timeout'),30000)
    return()=>clearTimeout(timer)
  },[index,retry,state])
  useEffect(()=>{
    if(state!=='ready'||(navigator as Navigator & {connection?:{saveData?:boolean}}).connection?.saveData) return
    // Bound speculative downloads to the neighboring originals only.
    const adjacent=[images[index-1],images[index+1]].filter(Boolean).map(item=>{
      const image=new Image();image.referrerPolicy='no-referrer';image.src=item.src;return image
    })
    return()=>{adjacent.forEach(image=>{image.src=''})}
  },[index,state,images])
  const distance=()=>{const points=[...pointers.current.values()];return points.length===2?Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y):0}

  useEffect(()=>{
    const handle=(event:KeyboardEvent)=>{
      if(event.key==='ArrowLeft'){event.preventDefault();setIndex(i=>Math.max(0,i-1))}
      if(event.key==='ArrowRight'){event.preventDefault();setIndex(i=>Math.min(images.length-1,i+1))}
    }
    window.addEventListener('keydown',handle)
    return()=>window.removeEventListener('keydown',handle)
  },[images.length])
  return createPortal(<div role="dialog" aria-modal="true" aria-label="Enlarged screenshot" className="ui-scope screenshot-gallery fixed inset-0 z-50 bg-black/95 flex flex-col p-4" onClick={onClose}>
    <div className="flex items-center justify-center gap-3 flex-wrap shrink-0 pb-3" onClick={e=>e.stopPropagation()}>
      <button disabled={index===0} onClick={()=>setIndex(index-1)}>Previous</button>
      <span aria-live="polite">{index+1} / {images.length}</span>
      <button disabled={index===images.length-1} onClick={()=>setIndex(index+1)}>Next</button>
      <button aria-label="Zoom out" disabled={zoom<=1} onClick={()=>setZoom(z=>Math.max(1,z-.5))}>−</button>
      <button onClick={()=>setZoom(1)}>Fit · {Math.round(zoom*100)}%</button>
      <button aria-label="Zoom in" disabled={zoom>=4} onClick={()=>setZoom(z=>Math.min(4,z+.5))}>+</button>
      <button aria-label="Close enlarged screenshot" onClick={onClose}>Close</button>
    </div>
    <div ref={viewport} className="gallery-viewport flex-1 min-h-0 overflow-auto" onClick={e=>e.stopPropagation()}
      onDoubleClick={()=>setZoom(z=>z===1?2:1)}
      onPointerDown={e=>{
        if(e.target instanceof HTMLElement&&e.target.closest('button')) return
        e.currentTarget.setPointerCapture(e.pointerId)
        pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY})
        if(pointers.current.size===2) gesture.current={distance:distance(),zoom}
      }}
      onPointerMove={e=>{
        const previous=pointers.current.get(e.pointerId);if(!previous)return
        pointers.current.set(e.pointerId,{x:e.clientX,y:e.clientY})
        if(pointers.current.size===2 && gesture.current.distance>0) setZoom(Math.min(4,Math.max(1,gesture.current.zoom*distance()/gesture.current.distance)))
        else if(zoom>1){e.currentTarget.scrollLeft+=previous.x-e.clientX;e.currentTarget.scrollTop+=previous.y-e.clientY}
      }}
      onPointerUp={e=>{pointers.current.delete(e.pointerId)}} onPointerCancel={()=>pointers.current.clear()}>
      {state==='loading'&&<p role="status" className="text-center p-4">Loading original image…</p>}
      {state==='error'||state==='timeout'?<div role="alert" className="text-center p-4">{state==='timeout'?'Original image loading timed out.':'Original image could not load.'} <button onClick={()=>setView(v=>({...v,state:'loading',retry:v.retry+1}))}>Retry original</button></div>:
      <img key={`${index}:${retry}`} src={current.src} alt={current.alt||'Screenshot'} referrerPolicy="no-referrer" onLoad={()=>setState('ready')} onError={()=>setState('error')} draggable={false} style={{display:state==='ready'?'block':'none',width:zoom===1?'auto':`${zoom*100}%`,maxWidth:zoom===1?'100%':'none',maxHeight:zoom===1?'100%':'none',margin:'0 auto',objectFit:'contain'}}/>}
    </div>
    <p className="gallery-caption text-center text-sm text-gray-400 pt-2 shrink-0">{current.alt}</p>
  </div>,document.body)
}
