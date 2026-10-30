import {TaskProgress} from '../components/TaskStatus'
import ContentDates from '../components/ContentDates'
import SourceAccessNotice,{sourceBlocked} from '../components/SourceAccessNotice'
import { lazy, useState, useEffect, useRef } from 'react'
import {OptionalTool} from '../components/DeferredView'
const LocalPodcastUpload=lazy(()=>import('../components/LocalPodcastUpload'))
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Play, FileText, MessageSquare, Loader2, CheckCircle, Trash2, RefreshCw, Tag, Sparkles } from 'lucide-react'
import { ApiError, fetchPodcast, fetchPodcasts, fetchEpisodes, processEpisode, deleteEpisode, resummarizeEpisode, type Podcast, type Episode } from '../lib/api'
import { useToast } from '../components/Toast'
import { useStore } from '../lib/store'
import { markSeen, isNewItem } from '../lib/seen'
import { fetchEpisode } from '../lib/api'
import LoadError from '../components/LoadError'
import { useWarmCache, getCache, getCacheAge, setCache, CacheKeys } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { prefetchSummary } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'

function cachedHasMore(rows:Episode[],count?:number) {
  return rows.length>0 && (rows.length%50===0 || (count===undefined?rows.length>=12:rows.length<count))
}

export default function Episodes() {
  const { pid } = useParams<{ pid: string }>()
  const cachedPodcast = () => getCache<Podcast>(CacheKeys.PODCAST(pid!))
    || getCache<Podcast[]>(CacheKeys.PODCASTS)?.find(item => item.pid === pid) || null
  const [podcast, setPodcast] = useState<Podcast | null>(cachedPodcast)
  const [episodes, setEpisodes] = useState<Episode[]>(() => getCache(CacheKeys.EPISODES(pid!)) || [])
  const [loading, setLoading] = useState(() => !getCache(CacheKeys.EPISODES(pid!)))
  const removedEpisodes = useRef(new Set<string>())
  const ownCache = useRef<Episode[] | null>(null)
  const updatedEpisodes = useRef(new Map<string, Episode>())
  const addedEpisodes = useRef(new Set<string>())
  function reconcileEpisodes(rows: Episode[]) {
    const ids = new Set(rows.map(row => row.eid))
    return [...[...addedEpisodes.current].filter(id => !ids.has(id)).map(id => updatedEpisodes.current.get(id)!),
      ...rows.map(row => updatedEpisodes.current.get(row.eid) || row)]
      .filter(row => !removedEpisodes.current.has(row.eid))
  }
  useWarmCache<Episode[]>(CacheKeys.EPISODES(pid!),value=>{if(value===ownCache.current)return;setEpisodes(() => reconcileEpisodes(value));setLoading(false);setError('');const cached=cachedPodcast();if(cached)setPodcast(cached);setHasMore(cachedHasMore(value,cached?.episode_count))})
  const [error, setError] = useState('')
  const [refreshWarning,setRefreshWarning] = useState('')
  const [errorSource, setErrorSource] = useState<'initial' | 'more'>('initial')
  usePageTiming('episodes', !loading && !error && (episodes[0]?.pid === pid || podcast?.pid === pid), CacheKeys.EPISODES(pid!), !!error)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(() => {
    const cached = getCache<Episode[]>(CacheKeys.EPISODES(pid!))
    return !!cached && cachedHasMore(cached,cachedPodcast()?.episode_count)
  })
  const completedJobsRef = useRef(new Set<string>())
  const [pendingActions, setPendingActions] = useState<Record<string,string>>({})
  const actionLocks = useRef(new Set<string>())
  const [metadataError,setMetadataError] = useState('')
  const [metadataLoading,setMetadataLoading] = useState(false)
  const metadataVersion = useRef(0)
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { jobs, updateJob } = useStore()
  const currentPid = useRef(pid)
  currentPid.current = pid
  const loadVersion = useRef(0)

  function beginAction(eid: string, action: string) {
    if (actionLocks.current.has(eid)) return false
    actionLocks.current.add(eid)
    setPendingActions(previous=>({...previous,[eid]:action}))
    return true
  }
  function finishAction(eid: string) {
    actionLocks.current.delete(eid)
    setPendingActions(previous=>{const next={...previous};delete next[eid];return next})
  }
  function saveEpisodes(rows:Episode[],owner=getAccountId()) {
    ownCache.current=rows
    setCache(CacheKeys.EPISODES(pid!),rows,owner)
  }
  function changeEpisodes(update: (previous:Episode[])=>Episode[]) {
    const owner=getAccountId()
    setEpisodes(previous=>{
      const rows=update(previous).filter(row=>!removedEpisodes.current.has(row.eid))
      const prior = new Map(previous.map(row => [row.eid, row]))
      for (const row of rows) {
        if (prior.get(row.eid) !== row) updatedEpisodes.current.set(row.eid, row)
        if (!prior.has(row.eid)) addedEpisodes.current.add(row.eid)
      }
      saveEpisodes(rows,owner)
      return rows
    })
  }
  async function loadMetadata() {
    if(!pid)return
    const version=++metadataVersion.current, owner=getAccountId(), requestedPid=pid
    const current=()=>version===metadataVersion.current&&currentPid.current===requestedPid&&owner===getAccountId()
    setMetadataLoading(true);setMetadataError('')
    try {
      const data=await fetchPodcast(pid)
      if(current()){setPodcast(data);setCache(CacheKeys.PODCAST(pid),data,owner)}
    } catch(error) {
      if(current())setMetadataError('Could not load podcast details: '+(error instanceof Error?error.message:'Please retry.'))
    } finally {if(current())setMetadataLoading(false)}
  }

  
  // Helper to find active job for an episode
  function getActiveJob(eid: string) {
    return jobs.find(job => 
      job.episode_id === eid && 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
  }
  
  useEffect(() => {
    if (!pid) return
    updatedEpisodes.current.clear()
    addedEpisodes.current.clear()
    const cached = getCache<Episode[]>(CacheKeys.EPISODES(pid))
    setEpisodes(cached || [])
    const metadata = cachedPodcast()
    setPodcast(metadata)
    setMetadataError('')
    setMetadataLoading(false)
    if(!metadata)void loadMetadata()
    setHasMore(!!cached && cachedHasMore(cached,metadata?.episode_count))
    setLoading(!cached)
    setLoadingMore(false)
    completedJobsRef.current.clear()
    seenMarkedRef.current = false
    void loadData()
    return () => { loadVersion.current += 1; metadataVersion.current += 1 }
  }, [pid])

  const seenMarkedRef = useRef(false)
  useEffect(() => {
    if (episodes.length > 0 && !seenMarkedRef.current) {
      seenMarkedRef.current = true
      markSeen(episodes.map(e => e.eid))
    }
  }, [episodes])
  
  function episodeError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 401) return 'Your session has expired. Please sign in again.'
      if (err.status === 404) return 'This podcast is no longer available in your account.'
      return `The episode service is unavailable (HTTP ${err.status}). Please retry.`
    }
    return 'The episode connection was interrupted or timed out. Please retry.'
  }

  async function loadData() {
    if (!pid) return
    const requestedPid = pid
    const owner = getAccountId()
    const version = ++loadVersion.current
    const current = () => version === loadVersion.current && currentPid.current === requestedPid && owner === getAccountId()
    setError('')
    setErrorSource('initial')
    setRefreshWarning('')
    const key=CacheKeys.EPISODES(pid), cached=getCache<Episode[]>(key)
    setLoading(!cached)
    if(cached && (getCacheAge(key) ?? Infinity)<60000) {
      setEpisodes(() => reconcileEpisodes(cached))
      const count=cachedPodcast()?.episode_count
      setHasMore(cachedHasMore(cached,count))
      return
    }
    try {
      const data = await fetchEpisodes(pid)
      if (!current()) return
      setEpisodes(() => {
        const rows = reconcileEpisodes(data)
        saveEpisodes(rows, owner)
        return rows
      })
      // A full page may have a successor even if metadata is unavailable/stale.
      setHasMore(data.length === 50)
    } catch (err) {
      if (current()) {
        const available=getCache<Episode[]>(CacheKeys.EPISODES(pid))
        if(available){setEpisodes(() => reconcileEpisodes(available));setRefreshWarning('Showing saved episodes. Live refresh is unavailable.')}
        else {
          setError(episodeError(err))
          // The collection's bounded previews can still recover a failed page
          // read. Keep this fallback off the successful opening path.
          void fetchPodcasts().catch(()=>{})
        }
      }
    } finally {
      if (current()) { setLoading(false) }
    }
  }

  async function loadMore() {
    if (!pid || loadingMore || loading) return
    const requestedPid = pid
    const owner = getAccountId()
    const version = loadVersion.current
    const current = () => version === loadVersion.current && requestedPid === currentPid.current && owner === getAccountId()
    setLoadingMore(true)
    setErrorSource('more')
    setError('')
    try {
      const next = await fetchEpisodes(pid, episodes.length)
      if (!current()) return
      setEpisodes(previous => {
        const ids=new Set(previous.map(row=>row.eid))
        const rows=[...previous,...next.filter(row=>!ids.has(row.eid))].filter(row=>!removedEpisodes.current.has(row.eid))
        saveEpisodes(rows,owner)
        return rows
      })
      setHasMore(next.length === 50)
    } catch (err) { if (current()) setError(episodeError(err)) }
    finally { if (current()) setLoadingMore(false) }
  }

  useEffect(() => {
    for (const job of jobs) {
      if (job.status !== 'completed' || !job.episode_id || completedJobsRef.current.has(job.job_id)) continue
      if (!episodes.some(episode => episode.eid === job.episode_id)) continue
      completedJobsRef.current.add(job.job_id)
      const owner=getAccountId(),requestedPid=pid
      void fetchEpisode(job.episode_id).then(fresh => {
        if(owner===getAccountId()&&currentPid.current===requestedPid)
          changeEpisodes(previous => previous.map(episode => episode.eid === fresh.eid ? fresh : episode))
      }).catch(() => completedJobsRef.current.delete(job.job_id))
    }
  }, [jobs, episodes])
  
  async function handleSubmit(episode: Episode, regenerate=false) {
    if((!regenerate&&!podcast) || getActiveJob(episode.eid) || !beginAction(episode.eid,regenerate?'regenerate':'process'))return
    const owner=getAccountId()
    const operation=regenerate?'Re-summarization':'Processing'
    try {
      const episodeUrl=podcast?.platform==='local' ? `local://${episode.eid}`
        : ['apple','spotify'].includes(podcast?.platform||'') ? `apple://${episode.eid}`
        : `https://www.xiaoyuzhoufm.com/episode/${episode.eid}`
      const result=await (regenerate ? resummarizeEpisode(episode.eid) : processEpisode(episodeUrl))
      if(owner!==getAccountId())return
      updateJob({job_id:result.job_id,created_at:Date.now()/1000,revision:0,status:'pending',progress:0,
        message:regenerate?'Re-summarizing...':'Starting...',episode_id:episode.eid,episode_title:episode.title})
      addToast({type:'success',title:`${operation} started`,message:episode.title})
    } catch(error) {
      if(owner===getAccountId())addToast({type:'error',title:`${operation} could not start`,message:error instanceof Error?error.message:'Please retry.'})
    } finally {finishAction(episode.eid)}
  }

  async function handleDelete(episode: Episode) {
    if(actionLocks.current.has(episode.eid))return
    if (!confirm(`Delete "${episode.title}"?\n\nThis will also delete any transcript and summary.`)) {
      return
    }
    
    if(!beginAction(episode.eid,'delete'))return
    const owner=getAccountId(),requestedPid=pid
    try {
      await deleteEpisode(episode.eid)
      if(owner!==getAccountId())return
      removedEpisodes.current.add(episode.eid)
      if(currentPid.current===requestedPid)changeEpisodes(previous => previous.filter(e => e.eid !== episode.eid))
      addToast({
        type: 'success',
        title: 'Episode deleted',
        message: episode.title,
      })
    } catch (err) {
      if(owner!==getAccountId())return
      console.error('Failed to delete episode:', err)
      addToast({
        type: 'error',
        title: 'Failed to delete episode',
        message: err instanceof Error ? err.message : undefined,
      })
    } finally {
      finishAction(episode.eid)
    }
  }
  
  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    return `${mins} min`
  }
  
  return (
    <div className="space-y-4 md:space-y-6">
      {error && <LoadError message={error} onRetry={() => { void (errorSource === 'more' ? loadMore() : loadData()) }} />}
      {metadataError && <LoadError message={metadataError} onRetry={() => void loadMetadata()} />}
      <div className="flex items-center gap-3 md:gap-4">
        <button
          aria-label="Go back"
            onClick={() => navigate(-1)}
          className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="min-w-0">
          <h1 className="page-title text-lg md:text-2xl font-bold text-white line-clamp-1">{podcast?.title || 'Episodes'}</h1>
          <p className="text-sm md:text-base text-gray-400">{loading ? 'Loading episodes…' : `${episodes.length}${hasMore && (podcast?.episode_count||0)>episodes.length ? ` of ${podcast!.episode_count}` : ''} episodes`}</p>
        </div>
      </div>
      {metadataLoading && <p role="status" className="text-sm text-gray-400">Loading podcast details…</p>}

      {podcast?.platform === 'local' && <OptionalTool fallback={<p role="status">Loading upload tools…</p>}>
        <LocalPodcastUpload onUploaded={result=>{
          if(currentPid.current!==pid)return
          changeEpisodes(previous=>[result.episode,...previous.filter(row=>row.eid!==result.episode.eid)])
        }}/>
      </OptionalTool>}

      {refreshWarning && <p role="status" className="text-sm text-gray-400">{refreshWarning}</p>}
      {loading && <div role="status" className="flex items-center gap-2 p-4 text-sm text-gray-400">
        <Loader2 size={18} className="animate-spin text-indigo-400" />
        Loading episodes…
      </div>}
      {!loading && !error && episodes.length === 0 && <p className="text-gray-400">No episodes saved yet.</p>}
      {/* Episodes list */}
      <div className="space-y-3">
        {episodes.map((episode) => (
          <div
            key={episode.eid}
            data-episode-id={episode.eid}
            onClick={episode.has_summary ? () => navigate(`/viewer/${episode.eid}`) : undefined}
            onPointerEnter={() => { if (episode.has_summary) prefetchSummary(episode.eid) }}
            onTouchStart={() => { if (episode.has_summary) prefetchSummary(episode.eid) }}
            className={`p-3 md:p-4 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors${episode.has_summary ? ' cursor-pointer' : ''}`}
          >
            <div className="flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-white mb-1 line-clamp-2 text-sm md:text-base">
                  {episode.title}
                </h3>
                <div className="flex flex-wrap items-center gap-2 md:gap-4 text-xs md:text-sm text-gray-400">
                  <ContentDates published={episode.pub_date} imported={episode.created_at} local={podcast?.platform === "local"} />
                  <span>{formatDuration(episode.duration)}</span>
                  
                  {/* Status indicators */}
                  {episode.has_transcript && (
                    <span className="flex items-center gap-1 text-green-500">
                      <FileText size={12} className="md:w-3.5 md:h-3.5" />
                      <span className="hidden sm:inline">Transcript</span>
                    </span>
                  )}
                  {episode.has_summary && (
                    <span className={`flex items-center gap-1 ${episode.quality_status === "needs_review" ? "text-amber-300" : "text-purple-500"}`}>
                      <MessageSquare size={12} className="md:w-3.5 md:h-3.5" />
                      <span>{episode.quality_status === "needs_review" ? "Summary needs review" : "Summary"}</span>
                      <span className="text-gray-400 ml-1">
                        ({episode.topics_count} <Tag size={10} className="inline" />, {episode.key_points_count} pts)
                      </span>
                    </span>
                  )}
                  {!episode.has_transcript && !episode.has_summary && isNewItem(episode.eid) && (
                    <span className="flex items-center gap-1 text-cyan-400">
                      <Sparkles size={12} className="md:w-3.5 md:h-3.5" />
                      <span className="hidden sm:inline">Newly Added</span>
                    </span>
                  )}
                </div>
                <SourceAccessNotice compact status={episode.source_status} message={episode.source_message} episodeId={episode.eid}/>
              </div>
              
              <div className="collection-actions" onClick={e => e.stopPropagation()}>
                {(() => {
                  const activeJob = getActiveJob(episode.eid)
                  
                  if (episode.has_summary) {
                    return (
                      <>
                        <button
                          aria-label={`Re-process ${episode.title}`}
                          onClick={() => handleSubmit(episode,true)}
                          disabled={!!pendingActions[episode.eid] || !!activeJob || sourceBlocked(episode.source_status) && episode.key_points_count===0}
                          className="ui-button ui-button-icon-mobile"
                          title={sourceBlocked(episode.source_status) && episode.key_points_count===0 ? episode.source_message : "Re-process episode"}
                        >
                          {pendingActions[episode.eid] === 'regenerate' ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <RefreshCw size={16} />
                          )}
                          <span className="hidden sm:inline">Re-Process</span>
                        </button>
                        <Link
                          to={`/viewer/${episode.eid}`}
                          onFocus={() => prefetchSummary(episode.eid)}
                          className="ui-button ui-button-primary"
                        >
                          <CheckCircle size={16} />
                          View
                        </Link>
                      </>
                    )
                  }
                  
                  if (activeJob) {
                    // Show processing progress
                    return (
                      <div className="collection-task"><TaskProgress status={activeJob.status} progress={activeJob.progress} startedAt={activeJob.started_at} message={activeJob.message} compact/></div>
                    )
                  }
                  
                  return (
                    <button
                      onClick={() => handleSubmit(episode)}
                      disabled={!podcast || !!pendingActions[episode.eid] || sourceBlocked(episode.source_status) && !episode.has_transcript}
                      className="ui-button"
                    >
                      {pendingActions[episode.eid] === 'process' ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Play size={16} />
                      )}
                      {sourceBlocked(episode.source_status) && !episode.has_transcript ? 'Source access required' : 'Process'}
                    </button>
                  )
                })()}
                
                {/* Delete button */}
                <button
                  onClick={() => handleDelete(episode)}
                  disabled={!!pendingActions[episode.eid]}
                  className="ui-button ui-button-icon ui-button-danger"
                  title="Delete episode"
                >
                  {pendingActions[episode.eid] === 'delete' ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                </button>
              </div>
            </div>
          </div>
        ))}
        {hasMore && <button disabled={loadingMore} onClick={() => { void loadMore() }} className="px-4 py-2 bg-dark-surface border border-dark-border rounded-lg text-indigo-300 disabled:opacity-50">{loadingMore ? 'Loading...' : 'Load more episodes'}</button>}
      </div>
    </div>
  )
}
