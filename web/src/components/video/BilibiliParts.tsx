import {useEffect,useRef,useState} from 'react'
import {Link,useParams} from 'react-router-dom'
import {authFetch,type VideoTask} from '../../lib/api'
import {getAuthGeneration} from '../../lib/auth'
import {requestWithDeadline} from '../../lib/requestDeadline'

type Part={page:number;title:string;url:string;task_id?:string|null;status:string;progress:number;error?:string}
const active=new Set(['pending','parsing','downloading','transcribing','summarizing','saving','running','queued'])
const selectable=(part:Part)=>['not_started','discovered','failed','cancelled','pending'].includes(part.status)
const labels:Record<string,string>={not_started:'Not processed',discovered:'Not processed',success:'Ready',failed:'Failed',cancelled:'Cancelled',pending:'Waiting',queued:'Queued',parsing:'Reading source',downloading:'Downloading',transcribing:'Transcribing',summarizing:'Summarizing',saving:'Saving',running:'Processing'}

export default function BilibiliParts({metadata}: {metadata:NonNullable<VideoTask['source_metadata']>}) {
  const {taskId=''}=useParams<{taskId:string}>()
  const [parts,setParts]=useState<Part[]>([]),[selected,setSelected]=useState<Set<number>>(new Set())
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const mounted=useRef(false),read=useRef<AbortController>(),write=useRef<AbortController>(),submitting=useRef(false)
  const base=`/api/video-notes/collections/${encodeURIComponent(taskId)}/parts`
  async function refresh() {
    read.current?.abort()
    const controller=new AbortController(),generation=getAuthGeneration();read.current=controller
    setLoading(true)
    try {
      const {response,data}=await requestWithDeadline(async signal=>{
        const response=await authFetch(base,{signal})
        return {response,data:await response.json().catch(()=>null)}
      },{signal:controller.signal,timeout:15000})
      if(!response.ok||!Array.isArray(data?.parts))throw new Error(typeof data?.detail==='string'?data.detail:'Cannot load collection statuses')
      if(!mounted.current||controller.signal.aborted||generation!==getAuthGeneration())return
      setParts(data.parts);setSelected(previous=>new Set([...previous].filter(page=>data.parts.some((part:Part)=>part.page===page&&selectable(part)))))
      setError('')
    } catch(reason) {
      if(mounted.current&&!controller.signal.aborted&&generation===getAuthGeneration())setError(reason instanceof Error?reason.message:'Cannot load collection statuses')
    } finally {
      if(read.current===controller)read.current=undefined
      if(mounted.current&&!controller.signal.aborted)setLoading(false)
    }
  }
  useEffect(()=>{
    mounted.current=true
    const reset=()=>{
      read.current?.abort();write.current?.abort();submitting.current=false
      setBusy(false);setMessage('');setError('');setParts([]);setSelected(new Set());void refresh()
    }
    reset();window.addEventListener('xyz:session-changed',reset)
    return()=>{mounted.current=false;read.current?.abort();write.current?.abort();window.removeEventListener('xyz:session-changed',reset)}
  },[taskId])
  const working=parts.some(part=>active.has(part.status))
  useEffect(()=>{
    if(!working||busy)return
    const timer=setInterval(()=>{if(!read.current&&document.visibilityState!=='hidden')void refresh()},15000)
    return()=>clearInterval(timer)
  },[working,busy,taskId])
  async function processSelected() {
    if(submitting.current||!selected.size||loading)return
    submitting.current=true;setBusy(true);setError('');setMessage('')
    read.current?.abort()
    const generation=getAuthGeneration(),controller=new AbortController();write.current=controller
    const pages=parts.filter(part=>selected.has(part.page)&&selectable(part));let accepted=0
    try {
      for(const part of pages) {
        if(controller.signal.aborted||generation!==getAuthGeneration())break
        const {response,data}=await requestWithDeadline(async signal=>{
          const response=await authFetch(`${base}/${part.page}/process`,{method:'POST',signal})
          return {response,data:await response.json().catch(()=>null)}
        },{signal:controller.signal,timeout:60000,message:'Queue confirmation timed out. The part may already be processing.'})
        if(!response.ok||!data?.task_id)throw new Error(`P${part.page}: ${typeof data?.detail==='string'?data.detail:'Queue confirmation was not received.'}`)
        if(controller.signal.aborted||!mounted.current||generation!==getAuthGeneration())break
        accepted++
        setSelected(previous=>{const next=new Set(previous);next.delete(part.page);return next})
        setParts(previous=>previous.map(row=>row.page===part.page?{...row,task_id:data.task_id,status:'pending'}:row))
        setMessage(`${accepted} of ${pages.length} confirmed. Processing continues in the task queue.`)
      }
      if(!controller.signal.aborted&&mounted.current&&generation===getAuthGeneration())await refresh()
    } catch(reason) {
      if(mounted.current&&!controller.signal.aborted&&generation===getAuthGeneration())setError(`${reason instanceof Error?reason.message:'Could not confirm submission.'} Remaining parts were not submitted. Refresh statuses before retrying.`)
    } finally {
      if(write.current===controller)submitting.current=false
      if(mounted.current&&!controller.signal.aborted)setBusy(false)
    }
  }
  if((metadata.bilibili_parts?.length||0)<2)return null
  return <section aria-label="Bilibili collection parts" className="mb-5 rounded-lg border border-dark-border p-3 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold">Collection · {metadata.bilibili_parts?.length} parts</h2>
      <button className="reader-action" disabled={busy||loading} onClick={()=>void refresh()}>Refresh statuses</button>
    </div>
    <p className="mt-2 mb-2 text-gray-400">Current: P{metadata.bilibili_part?.page}. Select other parts to process using this video's settings. Each has its own summary and progress.</p>
    {loading&&<p role="status">Loading part statuses…</p>}
    {error&&<p role="alert" className="mt-2 mb-2 text-red-300">{error}</p>}
    {message&&<p role="status" className="mt-2 mb-2 text-indigo-300">{message}</p>}
    <div className="max-h-64 overflow-y-auto divide-y divide-dark-border" aria-busy={loading}>
      {parts.map(part=><div key={part.page} className="flex flex-wrap items-center gap-3 py-3">
        <label className="flex min-w-0 flex-1 items-start gap-2">
          <input className="mt-1 h-4 w-4 shrink-0" type="checkbox" checked={selected.has(part.page)} disabled={busy||loading||!selectable(part)||part.page===metadata.bilibili_part?.page}
            onChange={event=>setSelected(previous=>{const next=new Set(previous);event.target.checked?next.add(part.page):next.delete(part.page);return next})}/>
          <span className="min-w-0 break-words"><span>{part.title}</span><span className="mt-1 block text-gray-400">{labels[part.status]||part.status}{active.has(part.status)&&part.progress>0?` · ${Math.round(part.progress)}%`:''}{part.page===metadata.bilibili_part?.page?' · Current part':''}</span>
            {part.status==='failed'&&part.error&&<span className="block text-red-300">{part.error}</span>}
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {part.task_id&&<Link className="reader-action" to={`/videos/${part.task_id}`}>{part.status==='success'?'Read summary':'View progress'}</Link>}
          <a className="reader-action" href={part.url} target="_blank" rel="noopener noreferrer">Original ↗</a>
        </div>
      </div>)}
    </div>
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button className="reader-action" disabled={busy||loading||!parts.length} onClick={()=>setSelected(new Set(parts.filter(part=>part.page!==metadata.bilibili_part?.page&&selectable(part)).map(part=>part.page)))}>Select unprocessed</button>
      <button className="reader-action" disabled={busy||!selected.size} onClick={()=>setSelected(new Set())}>Clear selection</button>
      <button className="ui-button" disabled={busy||loading||!!error||!selected.size} onClick={()=>void processSelected()}>{busy?'Submitting…':`Process selected (${selected.size})`}</button>
    </div>
  </section>
}
