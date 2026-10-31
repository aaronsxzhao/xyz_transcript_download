import {useEffect, useRef, useState} from 'react'
/** Animate only progress already reported by the server; never invent work. */
export function useSmoothedProgress(target:number, attempt:string) {
  const [value,setValue]=useState(target)
  const displayed=useRef(target), previousAttempt=useRef(attempt)
  useEffect(()=>{
    const reset=attempt!==previousAttempt.current
    previousAttempt.current=attempt
    let frame=0
    const publish=(v:number)=>{displayed.current=v;setValue(v)}
    if(reset || target<displayed.current || document.hidden ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || typeof requestAnimationFrame==='undefined') {
      publish(target);return
    }
    const from=displayed.current, start=performance.now()
    const tick=(now:number)=>{
      const t=Math.min(1,(now-start)/600)
      publish(from+(target-from)*(1-Math.pow(1-t,3)))
      if(t<1)frame=requestAnimationFrame(tick)
    }
    frame=requestAnimationFrame(tick)
    const restore=()=>{if(!document.hidden){cancelAnimationFrame(frame);publish(target)}}
    document.addEventListener('visibilitychange',restore)
    return()=>{cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',restore)}
  },[target,attempt])
  return value
}
