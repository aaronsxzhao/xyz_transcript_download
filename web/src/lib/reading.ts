import { useEffect } from 'react'
import { getAccountId } from './preferences'
import {getCache,hydrateCache} from './cache'

export function useReadingPosition(key: string, elementId?: string, ready = true) {
  useEffect(() => {
    if (!ready) return
    const el = elementId ? document.getElementById(elementId) : document.querySelector('main')
    if (!el) return
    const storageKey = `xyz_reading:${getAccountId()}:${key}`
    const owner=getAccountId(), saved=sessionStorage.getItem(storageKey)
    let target = Number(saved || 0)
    let active=true,interacted=false
    let restoring = target > 0
    const restore = () => { if (restoring) { el.scrollTop = target; if (el.scrollTop >= target - 1) restoring = false } }
    restore()
    if(saved===null && /^(podcast|video):/.test(key)) void hydrateCache('reading_history').then(()=>{
      if(!active||interacted||owner!==getAccountId()) return
      const [kind,...parts]=key.split(':')
      target=getCache<{id:string;kind:string;position?:number}[]>('reading_history')?.find(row=>row.kind===kind&&row.id===parts.join(':'))?.position||0
      restoring=target>0;restore()
    })
    const observer = new ResizeObserver(restore)
    if (el.firstElementChild) observer.observe(el.firstElementChild)
    const stop = () => { restoring = false;interacted=true }
    const timeout = setTimeout(stop, 5000)
    const save = () => { if (!restoring) sessionStorage.setItem(storageKey, String(el.scrollTop)) }
    el.addEventListener('scroll', save, { passive: true })
    el.addEventListener('wheel', stop, { passive: true })
    el.addEventListener('touchstart', stop, { passive: true })
    return () => { active=false; clearTimeout(timeout); save(); observer.disconnect(); el.removeEventListener('scroll', save); el.removeEventListener('wheel', stop); el.removeEventListener('touchstart', stop) }
  }, [key, elementId, ready])
}

export function useDialog(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]') || [])
    focusable()[0]?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close() }
      if (event.key === 'Tab') {
        const items = focusable(); const first = items[0]; const last = items[items.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus() }
  }, [open])
}
