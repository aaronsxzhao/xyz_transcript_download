import {useLayoutEffect, useRef} from 'react'
import {useLocation, useNavigate} from 'react-router-dom'

const isReader = (path:string) => /^\/(viewer|videos)\/[^/]+\/?$/.test(path)
export function readerOrigin(value:unknown):string | null {
  if(typeof value!=='string' || !/^\/(?:[?#]|$|settings(?:[?#]|$)|library(?:[?#]|$)|videos(?:[?#]|$)|podcasts(?:\/[^/?#]+\/episodes)?(?:[?#]|$))/.test(value)) return null
  return value
}
/** Keep the entry page across reader-to-reader transitions and reloads. */
export function useTrackReaderOrigin() {
  const location=useLocation(), navigate=useNavigate()
  const previous=useRef(location)
  useLayoutEffect(()=>{
    const before=previous.current
    previous.current=location
    if(!isReader(location.pathname) || readerOrigin(location.state?.readerOrigin)) return
    const origin=isReader(before.pathname)
      ? readerOrigin(before.state?.readerOrigin)
      : readerOrigin(before.pathname+before.search+before.hash)
    if(origin) navigate(location.pathname+location.search+location.hash,{replace:true,state:{...location.state,readerOrigin:origin}})
  },[location,navigate])
}
export function useReaderReturn() {
  const location=useLocation(), navigate=useNavigate()
  const origin=readerOrigin(location.state?.readerOrigin)||'/library'
  return ()=>navigate(origin,{replace:true})
}
