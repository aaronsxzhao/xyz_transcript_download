import {useEffect, useRef, useState} from 'react'
import {Link} from 'react-router-dom'
import {RefreshCw} from 'lucide-react'
import {fetchLibrary, type LibraryPage} from '../lib/api'
import {getCache, setCache, useWarmCache} from '../lib/cache'
import {getAccountId} from '../lib/preferences'
import LoadError from './LoadError'
import NoteCard from './NoteCard'

type Kind = '' | 'podcast' | 'video' | 'article'
export default function DashboardRecent({revision}: {revision:number}) {
  const [kind, setKind] = useState<Kind>('')
  return <section className="dashboard-recent" aria-label="Recently added">
    <div className="dashboard-section-heading dashboard-recent-heading">
      <div className="dashboard-recent-title"><h2>Recently added</h2>
        <div className="dashboard-recent-filters" role="group" aria-label="Recent content type">
          {(['','podcast','video','article'] as const).map(value=><button key={value} aria-pressed={kind===value} onClick={()=>setKind(value)}>{value===''?'All':value==='podcast'?'Podcasts':value==='video'?'Videos':'Articles'}</button>)}
        </div>
      </div>
      <Link to="/library" className="reader-action">View Library →</Link>
    </div>
    <RecentFeed key={kind} kind={kind} revision={revision}/>
  </section>
}

function RecentFeed({kind,revision}: {kind:Kind;revision:number}) {
  const key='library_page:dashboard_recent:v1:'+kind
  const [page,setPage]=useState<LibraryPage>(()=>getCache(key)||{items:[],next_cursor:null})
  const [loading,setLoading]=useState(true),[error,setError]=useState('')
  const controller=useRef<AbortController>(),confirmed=useRef(false),failedCursor=useRef('')
  useWarmCache<LibraryPage>(key,value=>{if(!confirmed.current)setPage(value)})
  async function load(cursor='') {
    if(cursor && controller.current)return
    controller.current?.abort()
    const request=new AbortController(),owner=getAccountId()
    controller.current=request
    const current=()=>controller.current===request && !request.signal.aborted && owner===getAccountId()
    setLoading(true);setError('')
    try {
      const result=await fetchLibrary(new URLSearchParams({limit:'12',sort:'newest',status:'completed',...(kind?{kind}:{})}).toString(),cursor,request.signal)
      if(!current())return
      if(!Array.isArray(result.items))throw new Error('Cannot load recent content')
      result.items=result.items.filter(item=>item.status==='completed')
      confirmed.current=true
      setPage(previous=>cursor?{...result,items:[...new Map([...previous.items,...result.items].map(item=>[item.kind+':'+item.id,item])).values()]}:result)
      if(!cursor)setCache(key,result,owner)
    } catch(reason) {
      if(current()){failedCursor.current=cursor;setError(reason instanceof Error?reason.message:'Cannot load recent content')}
    } finally {
      if(current()){controller.current=undefined;setLoading(false)}
    }
  }
  useEffect(()=>{void load();return()=>controller.current?.abort()},[revision])
  return <>
    <div className="dashboard-recent-status">
      <span role="status">{loading?'Updating…':`${page.items.length} loaded${page.next_cursor?' · More available':''}`} · Saved content, newest first</span>
      <button className="reader-action reader-action-icon" aria-label="Refresh recent content" disabled={loading} onClick={()=>void load()}><RefreshCw size={16} className={loading?'animate-spin':''}/></button>
    </div>
    {error&&<LoadError message={error} onRetry={()=>void load(failedCursor.current)}/>}
    <div className="dashboard-recent-notes" aria-busy={loading}>{page.items.map((item,index)=><NoteCard key={item.kind+':'+item.id} item={item} priority={index===0}/>)}</div>
    {!page.items.length&&!error&&!loading&&<p className="text-sm text-gray-400">No saved {kind==='article'?'articles':kind==='podcast'?'podcast summaries':kind==='video'?'video notes':'content'} yet.</p>}
    {page.next_cursor&&<div className="dashboard-recent-more"><button className="ui-button" disabled={loading} onClick={()=>void load(page.next_cursor!)}>{loading?'Loading…':'Load more'}</button></div>}
  </>
}
