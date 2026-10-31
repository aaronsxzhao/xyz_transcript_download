import {useEffect, useRef, useState} from 'react'
/** Animate reported work, preserving motion when another result arrives mid-frame. */
export function useSmoothedProgress(target:number, attempt:string) {
  const [value,setValue]=useState(target)
  const displayed=useRef(target), previousAttempt=useRef(attempt), velocity=useRef(0)
  useEffect(()=>{
    const reset=attempt!==previousAttempt.current
    previousAttempt.current=attempt
    let frame=0
    const publish=(v:number)=>{displayed.current=v;setValue(v)}
    if(reset || target<=displayed.current || document.hidden ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || typeof requestAnimationFrame==='undefined') {
      velocity.current=0;publish(target);return
    }
    const from=displayed.current, start=performance.now(), distance=target-from
    const duration=Math.min(900, Math.max(240, distance*25))
    // Monotone cubic Hermite: carry forward velocity, ease to rest, never overshoot.
    const slope=Math.min(3*distance, Math.max(0,velocity.current*duration))
    const tick=(now:number)=>{
      const t=Math.max(0, Math.min(1,(now-start)/duration))
      const eased=distance*(3*t*t-2*t*t*t)+slope*(t*t*t-2*t*t+t)
      velocity.current=(distance*(6*t-6*t*t)+slope*(3*t*t-4*t+1))/duration
      publish(from+eased)
      if(t<1)frame=requestAnimationFrame(tick)
    }
    frame=requestAnimationFrame(tick)
    const restore=()=>{if(!document.hidden){cancelAnimationFrame(frame);velocity.current=0;publish(target)}}
    document.addEventListener('visibilitychange',restore)
    return()=>{cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',restore)}
  },[target,attempt])
  return value
}
