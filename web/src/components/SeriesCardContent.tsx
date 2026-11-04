import {Video,ChevronDown} from 'lucide-react'
import {platformLabel} from '../lib/platformLabels'
import {getStatusText} from '../lib/statusUtils'
import {useEffect,useRef,useState} from 'react'
import {Link} from 'react-router-dom'
import CachedImage from './CachedImage'
import {authFetch} from '../lib/api'
import {getAuthGeneration} from '../lib/auth'
import {requestWithDeadline} from '../lib/requestDeadline'
import {seriesIdentity,type LibrarySeries} from '../lib/librarySeries'
import './SeriesCard.css'
type Part={page:number;title:string;task_id?:string|null;status:string}
export default function SeriesCard({group,priority=false,layout='recent'}:{group:LibrarySeries;priority?:boolean;layout?:'recent'|'grid'|'list'}) {
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
 const library=layout!=='recent'
 const saved=group.items.reduce((latest,row)=>row.date>latest?row.date:latest,'')
 return <article className="series-card" data-series={group.key} data-presentation={layout}>
  <div className={library?'series-card-heading library-card':'series-card-heading reading-history-card'} data-layout={layout} data-kind="video">
   <div className={library?'library-artwork':'reading-history-art'} aria-hidden="true">
    <CachedImage priority={priority} src={item.thumbnail||''} alt="" className={library?'library-cover-image':'series-cover'} fit="contain" fallback={<span className={library?'library-artwork-fallback':'cached-image-fallback note-card-fallback'} data-type="video"><Video size={library?36:24} strokeWidth={1.5}/></span>}/>
    {library&&<span className="library-media-badge"><Video size={13}/>Series</span>}
   </div>
   <div className={library?'series-copy library-card-body':'series-copy note-card-copy min-w-0 flex-1'}>
    {library&&<div className="library-card-meta"><span>{platformLabel(item.platform,'Video')}</span><time dateTime={item.published_at||saved}>{item.published_at?`Published ${item.published_at.slice(0,10)}`:saved?`Saved ${new Date(saved).toLocaleDateString()}`:''}</time></div>}
    <h2 className="font-semibold leading-snug line-clamp-2" title={group.title}>{group.title}</h2>
    <p className={`${library?'mt-2':'mt-1'} text-sm text-gray-400 truncate`}>{item.source}</p>
    {!library&&<p className="note-card-meta"><span>{platformLabel(item.platform,'Video')}</span>{item.published_at&&<time dateTime={item.published_at}>Published {item.published_at.slice(0,10)}</time>}{saved&&<time dateTime={saved}>Saved {new Date(saved).toLocaleDateString()}</time>}</p>}
    <div className={library?'series-footer library-card-footer':'series-footer flex items-center justify-between text-xs text-indigo-300 mt-2'}><span>{group.total>1?`${group.total} episodes`:'Series'}</span><button className="series-toggle" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'Hide episodes':'View episodes'} <ChevronDown size={14}/></button></div>
   </div>
  </div>
  {open&&<div className="series-episodes" aria-label={`${group.title} episodes`}>
   <div className="series-episode-toolbar"><span role="status">{loading?'Loading episode statuses…':`${unique.length} episodes${parts.length?'':' loaded'}`}</span><button className="reader-action" disabled={loading} onClick={()=>setRevision(value=>value+1)}>Refresh</button></div>
   {error&&<p role="alert">{error}</p>}
   <ol>{unique.map(part=>{
    const saved=available.get(part.page),id=part.task_id||saved?.id,ready=part.status==='success'||!!saved
    return <li key={part.page}><span className="series-part-number">P{part.page}</span><div><p>{part.title.replace(/^.*? · P\d+\/\d+\s*/, '') || part.title}</p><span className="series-meta">{ready?'Ready to read':part.status==='not_started'?'Not processed':getStatusText(part.status)}</span></div>{id&&<Link className="reader-action" to={`/videos/${id}`}>{ready?'Read summary':'View progress'} →</Link>}</li>
   })}</ol>
  </div>}
 </article>
}
