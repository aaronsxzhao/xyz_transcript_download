import {useEffect} from 'react'
import {getAccountId} from './preferences'

type Position = {top:number;href?:string;offset?:number}

/** Restore the entry row, rather than a reader offset or a loading placeholder. */
export function useListReturn(key:string, ready:boolean) {
  useEffect(()=>{
    if(!ready)return
    const main=document.querySelector('main')
    if(!main)return
    const owner=getAccountId(),storageKey=`xyz_reading:${owner}:${key}`
    let position:Position={top:0}
    try {
      const saved=JSON.parse(sessionStorage.getItem(storageKey) || '0')
      if(typeof saved==='number')position={top:Math.max(0,saved)}
      else if(saved && Number.isFinite(saved.top))position=saved
    } catch {}
    let restoring=true,frame=0,leaving=false
    const restore=()=>{
      if(!restoring)return
      const row=position.href ? main.querySelector<HTMLElement>(`[data-reader-href="${CSS.escape(position.href)}"]`) : null
      if(row && Number.isFinite(position.offset)) {
        let parent=row.parentElement
        while(parent && parent!==main) {
          if(parent instanceof HTMLDetailsElement)parent.open=true
          parent=parent.parentElement
        }
        position.top=main.scrollTop+row.getBoundingClientRect().top-position.offset!
      }
      main.scrollTop=position.top
    }
    const schedule=()=>{
      if(!restoring || frame)return
      frame=requestAnimationFrame(()=>{frame=0;restore()})
    }
    const save=()=>{
      if(owner!==getAccountId())return
      try {sessionStorage.setItem(storageKey,JSON.stringify(position))} catch {}
    }
    const stop=()=>{restoring=false;leaving=false;position={top:main.scrollTop}}
    const keydown=(e:KeyboardEvent)=>{
      if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' ','Tab'].includes(e.key))stop()
    }
    const scroll=()=>{if(!restoring && !leaving){position={top:main.scrollTop};save()}}
    const capture=(e:MouseEvent)=>{
      if(e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)return
      const target=e.target as Element,row=target.closest<HTMLElement>('[data-reader-href]')
      if(!row || target.closest('button,summary,input,select,textarea'))return
      const link=target.closest('a[href]')
      if(link && link.getAttribute('href')!==row.dataset.readerHref)return
      leaving=true
      position={top:main.scrollTop,href:row.dataset.readerHref,offset:row.getBoundingClientRect().top}
      save()
    }
    const resize=new ResizeObserver(schedule),mutation=new MutationObserver(schedule)
    if(main.firstElementChild)resize.observe(main.firstElementChild)
    mutation.observe(main,{childList:true,subtree:true})
    restore()
    main.addEventListener('click',capture,true)
    main.addEventListener('scroll',scroll,{passive:true})
    main.addEventListener('wheel',stop,{passive:true})
    main.addEventListener('touchstart',stop,{passive:true})
    main.addEventListener('pointerdown',stop,{passive:true})
    main.addEventListener('keydown',keydown)
    return ()=>{
      save();restoring=false;cancelAnimationFrame(frame);resize.disconnect();mutation.disconnect()
      main.removeEventListener('click',capture,true);main.removeEventListener('scroll',scroll)
      main.removeEventListener('wheel',stop);main.removeEventListener('touchstart',stop)
      main.removeEventListener('pointerdown',stop);main.removeEventListener('keydown',keydown)
    }
  },[key,ready])
}
