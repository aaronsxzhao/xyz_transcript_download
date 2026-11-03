import {useEffect,useRef,useState} from 'react'
import {Link} from 'react-router-dom'
import CachedImage from './CachedImage'
import {authFetch} from '../lib/api'
import {getAuthGeneration} from '../lib/auth'
import {requestWithDeadline} from '../lib/requestDeadline'
import {seriesIdentity,type LibrarySeries} from '../lib/librarySeries'
import './SeriesCard.css'
type Part={page:number;title:string;task_id?:string|null;status:string}
export default function SeriesCard({group,priority=false}:{group:LibrarySeries;priority?:boolean}) {
 const [open,setOpen]=useState(false),[parts,setParts]=useState<Part[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0)
 const request=useRef<AbortController>()
 const item=group.items[0]
 useEffect(()=>{
  if(!open)return
  const controller=new AbortController(),generation=getAuthGeneration();request.current=controller
  setLoading(true);setError('')
  const current=()=>!controller.signal.aborted&&generation===getAuthGeneration()
  void requestWithDeadline(async signal=>{
   const response=await authFetch(`/api/video-notes/collections/${encodeURIComponent(item.id)}/parts`,{signal})
   const data=await response.json()
   if(!response.ok||!Array.isArray(data.parts))throw new Error('Could not load all episodes. Your saved episodes are still available below.')
   return data.parts as Part[]
  },{signal:controller.signal}).then(value=>{if(current())setParts(value)}).catch(reason=>{if(current())setError(reason instanceof Error?reason.message:'Could not load episodes')}).finally(()=>{if(current())setLoading(false)})
  return()=>controller.abort()
 },[open,item.id,revision])
 useEffect(()=>{const reset=()=>{request.current?.abort();setParts([]);setOpen(false)};window.addEventListener('xyz:session-changed',reset);return()=>window.removeEventListener('xyz:session-changed',reset)},[])
 const available=new Map(group.items.map(i=>[seriesIdentity(i)?.part,i]))
 const episodes=parts.length?parts:group.items.map(i=>({page:seriesIdentity(i)?.part||1,title:seriesIdentity(i)?.label||i.title,task_id:i.id,status:'success'}))
 const unique=[...new Map(episodes.map(p=>[p.page,p])).values()].sort((a,b)=>a.page-b.page)
 return <article className="series-card" data-series={group.key}>
  <div className="series-card-heading">
   <CachedImage priority={priority} src={item.thumbnail||''} alt="" className="series-cover" fit="contain" fallback={<span aria-hidden="true">Series</span>}/>
   <div className="series-copy"><p className="series-meta">Series{group.total>1?` · ${group.total} episodes`:''}</p><h2>{group.title}</h2><p className="series-meta">{item.source}</p>
    <button className="ui-button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'Hide episodes':'View episodes'}</button>
   </div>
  </div>
  {open&&<div className="series-episodes" aria-label={`${group.title} episodes`}>
   <div className="series-episode-toolbar"><span role="status">{loading?'Loading episode statuses…':`${unique.length} episodes${parts.length?'':' loaded'}`}</span><button className="reader-action" disabled={loading} onClick={()=>setRevision(value=>value+1)}>Refresh</button></div>
   {error&&<p role="alert">{error}</p>}
   <ol>{unique.map(part=>{
    const saved=available.get(part.page),id=part.task_id||saved?.id,ready=part.status==='success'||!!saved
    return <li key={part.page}><span className="series-part-number">P{part.page}</span><div><p>{part.title}</p><span className="series-meta">{ready?'Ready to read':part.status==='not_started'?'Not processed':part.status}</span></div>{id&&<Link className="reader-action" to={`/videos/${id}`}>{ready?'Read summary':'View progress'} →</Link>}</li>
   })}</ol>
  </div>}
 </article>
}
