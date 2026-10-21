import ContentDates from '../components/ContentDates'
import SourceAccessNotice,{sourceBlocked} from '../components/SourceAccessNotice'
import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Play, FileText, MessageSquare, Loader2, CheckCircle, Trash2, RefreshCw, Tag, Sparkles, Upload } from 'lucide-react'
import { ApiError, fetchPodcasts, fetchEpisodes, processEpisode, deleteEpisode, resummarizeEpisode, uploadLocalPodcastAudio, type Podcast, type Episode } from '../lib/api'
import { useToast } from '../components/Toast'
import { useStore } from '../lib/store'
import { getStatusColor } from '../lib/statusUtils'
import { markSeen, isNewItem } from '../lib/seen'
import { fetchEpisode } from '../lib/api'
import LoadError from '../components/LoadError'
import { useWarmCache, getCache, getCacheAge, setCache, CacheKeys } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { prefetchSummary } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'

export default function Episodes() {
  const { pid } = useParams<{ pid: string }>()
  const cachedPodcast = () => getCache<Podcast>(CacheKeys.PODCAST(pid!))
    || getCache<Podcast[]>(CacheKeys.PODCASTS)?.find(item => item.pid === pid) || null
  const [podcast, setPodcast] = useState<Podcast | null>(cachedPodcast)
  const [episodes, setEpisodes] = useState<Episode[]>(() => getCache(CacheKeys.EPISODES(pid!)) || [])
  const [loading, setLoading] = useState(() => !getCache(CacheKeys.EPISODES(pid!)))
  useWarmCache<Episode[]>(CacheKeys.EPISODES(pid!),value=>{setEpisodes(value);setLoading(false);setError('');const cached=cachedPodcast();if(cached){setPodcast(cached);setHasMore(value.length<cached.episode_count)}})
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [refreshWarning,setRefreshWarning] = useState('')
  const [errorSource, setErrorSource] = useState<'initial' | 'more'>('initial')
  usePageTiming('episodes', !loading && !error && (episodes[0]?.pid === pid || podcast?.pid === pid), CacheKeys.EPISODES(pid!), !!error)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(() => {
    const cached = getCache<Episode[]>(CacheKeys.EPISODES(pid!))
    return !!cached && cached.length < (cachedPodcast()?.episode_count ?? cached.length)
  })
  const completedJobsRef = useRef(new Set<string>())
  const [processingEid, setProcessingEid] = useState<string | null>(null)
  const [regeneratingEid, setRegeneratingEid] = useState<string | null>(null)
  const [deletingEid, setDeletingEid] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { jobs, updateJob } = useStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const currentPid = useRef(pid)
  currentPid.current = pid
  const loadVersion = useRef(0)

  
  // Helper to find active job for an episode
  function getActiveJob(eid: string) {
    return jobs.find(job => 
      job.episode_id === eid && 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
  }
  
  useEffect(() => {
    if (!pid) return
    const cached = getCache<Episode[]>(CacheKeys.EPISODES(pid))
    setEpisodes(cached || [])
    const metadata = cachedPodcast()
    setPodcast(metadata)
    setHasMore(!!cached && cached.length < (metadata?.episode_count ?? cached.length))
    setLoading(!cached)
    setLoadingMore(false)
    completedJobsRef.current.clear()
    seenMarkedRef.current = false
    void loadData()
    return () => { loadVersion.current += 1 }
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
    setRetrying(false)
    setRefreshWarning('')
    const key=CacheKeys.EPISODES(pid), cached=getCache<Episode[]>(key)
    setLoading(!cached)
    if(!cached || !cachedPodcast()) void fetchPodcasts().catch(()=>{})
    if(cached && (getCacheAge(key) ?? Infinity)<60000) {
      setEpisodes(cached)
      const count=cachedPodcast()?.episode_count
      setHasMore(count===undefined?cached.length>=12:cached.length<count)
      return
    }
    try {
      let data: Episode[]
      try { data = await fetchEpisodes(pid) }
      catch (err) {
        // One fresh connection for transient read failures; never retry auth,
        // missing records, cancellation, or any mutation automatically.
        const available=getCache<Episode[]>(CacheKeys.EPISODES(pid))
        if(current() && available) {
          setEpisodes(available)
          setRefreshWarning('Showing saved episodes. Live refresh is unavailable.')
          return
        }
        if (!current() || !(err instanceof TypeError ||
          err instanceof Error && err.message.includes('timed out') ||
          err instanceof ApiError && [502, 503, 504].includes(err.status))) throw err
        setRetrying(true)
        data = await fetchEpisodes(pid)
      }
      if (!current()) return
      setEpisodes(data)
      setCache(CacheKeys.EPISODES(pid), data, owner)
      // A full page may have a successor even if metadata is unavailable/stale.
      setHasMore(data.length === 50)
    } catch (err) {
      if (current()) {
        const available=getCache<Episode[]>(CacheKeys.EPISODES(pid))
        if(available){setEpisodes(available);setRefreshWarning('Showing saved episodes. Live refresh is unavailable.')}
        else setError(episodeError(err))
      }
    } finally {
      if (current()) { setLoading(false); setRetrying(false) }
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
        const rows=[...previous,...next.filter(row=>!ids.has(row.eid))]
        setCache(CacheKeys.EPISODES(pid),rows,owner)
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
      void fetchEpisode(job.episode_id).then(fresh => {
        setEpisodes(previous => previous.map(episode => episode.eid === fresh.eid ? fresh : episode))
      }).catch(() => completedJobsRef.current.delete(job.job_id))
    }
  }, [jobs, episodes])
  
  async function handleProcess(episode: Episode) {
    setProcessingEid(episode.eid)
    try {
      const isLocal = podcast?.platform === 'local'
      const isApple = podcast?.platform === 'apple'
      const episodeUrl = isLocal
        ? `local://${episode.eid}`
        : isApple
          ? `apple://${episode.eid}`
          : `https://www.xiaoyuzhoufm.com/episode/${episode.eid}`
      const result = await processEpisode(episodeUrl)
      
      // Immediately add job to store for instant UI feedback
      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Starting...',
        episode_id: episode.eid,
        episode_title: episode.title,
      })
      
      addToast({
        type: 'success',
        title: 'Processing started',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to start processing:', err)
      addToast({
        type: 'error',
        title: 'Failed to start processing',
      })
    } finally {
      setProcessingEid(null)
    }
  }

  async function handleLocalUpload(file: File) {
    setUploading(true)
    try {
      const result = await uploadLocalPodcastAudio(file, {
        title: uploadTitle.trim(),
        description: uploadDescription.trim(),
      })
      if (result.podcast.pid === pid) {
        setEpisodes(prev => [result.episode, ...prev])
      } else {
        await loadData()
      }
      setUploadTitle('')
      setUploadDescription('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      addToast({ type: 'success', title: 'Audio uploaded', message: result.episode.title })
    } catch (err) {
      console.error('Failed to upload audio:', err)
      addToast({
        type: 'error',
        title: 'Upload failed',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setUploading(false)
    }
  }
  
  async function handleRegenerate(episode: Episode) {
    setRegeneratingEid(episode.eid)
    try {
      const result = await resummarizeEpisode(episode.eid)
      
      // Add job to store for instant UI feedback
      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Re-summarizing...',
        episode_id: episode.eid,
        episode_title: episode.title,
      })
      
      addToast({
        type: 'success',
        title: 'Re-summarization started',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to start re-summarization:', err)
      addToast({
        type: 'error',
        title: 'Failed to start re-summarization',
      })
    } finally {
      setRegeneratingEid(null)
    }
  }
  
  async function handleDelete(episode: Episode) {
    if (!confirm(`Delete "${episode.title}"?\n\nThis will also delete any transcript and summary.`)) {
      return
    }
    
    setDeletingEid(episode.eid)
    try {
      await deleteEpisode(episode.eid)
      setEpisodes(episodes.filter(e => e.eid !== episode.eid))
      addToast({
        type: 'success',
        title: 'Episode deleted',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to delete episode:', err)
      addToast({
        type: 'error',
        title: 'Failed to delete episode',
      })
    } finally {
      setDeletingEid(null)
    }
  }
  
  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    return `${mins} min`
  }
  
  return (
    <div className="space-y-4 md:space-y-6">
      {error && <LoadError message={error} onRetry={() => { void (errorSource === 'more' ? loadMore() : loadData()) }} />}
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
          <p className="text-sm md:text-base text-gray-400">{loading ? 'Loading episodes…' : `${episodes.length}${hasMore && podcast?.episode_count ? ` of ${Math.max(podcast.episode_count, episodes.length)}` : ''} episodes`}</p>
        </div>
      </div>

      {podcast?.platform === 'local' && (
        <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">Add More Local Audio</h2>
              <p className="text-sm text-gray-400">New uploads are added to this local podcast and can be processed like normal episodes.</p>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors"
            >
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              Upload Audio
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              type="text"
              value={uploadTitle}
              onChange={e => setUploadTitle(e.target.value)}
              placeholder="Optional title override"
              className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,.mp3,.m4a,.wav,.aac,.flac,.ogg,.opus,.mp4,.mpeg,.mpga"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) void handleLocalUpload(file)
              }}
            />
            <textarea
              value={uploadDescription}
              onChange={e => setUploadDescription(e.target.value)}
              placeholder="Optional description"
              rows={2}
              className="md:col-span-2 w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base resize-y"
            />
          </div>
        </div>
      )}
      
      {refreshWarning && <p role="status" className="text-sm text-gray-400">{refreshWarning}</p>}
      {loading && <div role="status" className="flex items-center gap-2 p-4 text-sm text-gray-400">
        <Loader2 size={18} className="animate-spin text-indigo-400" />
        {retrying ? 'Connection interrupted. Retrying once…' : 'Loading episodes…'}
      </div>}
      {!loading && !error && episodes.length === 0 && <p className="text-gray-400">No episodes saved yet.</p>}
      {/* Episodes list */}
      <div className="space-y-3">
        {episodes.map((episode) => (
          <div
            key={episode.eid}
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
              
              <div className="flex items-center gap-2 justify-end sm:justify-start" onClick={e => e.stopPropagation()}>
                {(() => {
                  const activeJob = getActiveJob(episode.eid)
                  
                  if (episode.has_summary) {
                    return (
                      <>
                        <button
                          onClick={() => handleRegenerate(episode)}
                          disabled={regeneratingEid === episode.eid || !!activeJob || sourceBlocked(episode.source_status) && episode.key_points_count===0}
                          className="flex items-center gap-2 px-3 py-2 bg-dark-hover hover:bg-dark-border text-gray-300 rounded-lg transition-colors disabled:opacity-50"
                          title={sourceBlocked(episode.source_status) && episode.key_points_count===0 ? episode.source_message : "Re-process episode"}
                        >
                          {regeneratingEid === episode.eid ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <RefreshCw size={16} />
                          )}
                          <span className="hidden sm:inline">Re-Process</span>
                        </button>
                        <Link
                          to={`/viewer/${episode.eid}`}
                          onFocus={() => prefetchSummary(episode.eid)}
                          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
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
                      <div className="flex items-center gap-3 px-4 py-2 bg-dark-hover rounded-lg min-w-[140px]">
                        <Loader2 size={16} className="animate-spin text-indigo-400" />
                        <div className="flex-1">
                          <div className="text-xs text-gray-400 mb-1">
                            {activeJob.message || activeJob.status}
                          </div>
                          <div className="h-1.5 bg-dark-border rounded-full overflow-hidden">
                            <div 
                              className={`h-full ${getStatusColor(activeJob.status)} transition-all duration-300`}
                              style={{ width: `${Math.min(activeJob.progress, 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    )
                  }
                  
                  return (
                    <button
                      onClick={() => handleProcess(episode)}
                      disabled={processingEid === episode.eid || sourceBlocked(episode.source_status) && !episode.has_transcript}
                      className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                    >
                      {processingEid === episode.eid ? (
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
                  disabled={deletingEid === episode.eid}
                  className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors disabled:opacity-50"
                  title="Delete episode"
                >
                  {deletingEid === episode.eid ? (
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
