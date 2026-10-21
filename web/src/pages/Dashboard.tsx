import CachedImage from '../components/CachedImage'
import LoadError from '../components/LoadError'
import { getAccountId } from '../lib/preferences'
import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Radio, FileText, MessageSquare, Loader2, Plus, ArrowRight, Bell, RefreshCw, X, Video, CheckCircle, Users } from 'lucide-react'
import { fetchStats, fetchRecentSummaries, processEpisode, fetchContentUpdates, dismissContentUpdates, type ContentUpdate, checkPodcastsForUpdates, checkVideoChannelsForUpdates, fetchRecentVideoTasks, cancelJob, cancelVideoTask, generateVideoNote, getVideoProcessingDefaults, getUserModelSettings, type Stats, type SummaryListItem, type ProcessingJob, type VideoTask } from '../lib/api'
import { useStore } from '../lib/store'
import { useWarmCache, getCache, setCache, CacheKeys } from '../lib/cache'
import { useToast } from '../components/Toast'
import { markSeen, shouldDismissCompleted } from '../lib/seen'
import SummaryCard from '../components/SummaryCard'
import ProcessingProgress from '../components/ProcessingProgress'
import { usePageTiming } from '../lib/pageTiming'
import { prefetchVideoNote } from '../lib/summaryPrefetch'

const VIDEO_QUEUE_STATUSES = new Set(['pending', 'parsing', 'downloading', 'transcribing', 'summarizing', 'saving', 'success', 'failed'])

function detectVideoPlatform(url: string): string {
  const u = url.toLowerCase()
  if (/bilibili\.com|b23\.tv/.test(u)) return 'bilibili'
  if (/youtube\.com|youtu\.be/.test(u)) return 'youtube'
  if (/douyin\.com|tiktok\.com/.test(u)) return 'douyin'
  if (/kuaishou\.com|kwai\.com/.test(u)) return 'kuaishou'
  return ''
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [summaries, setSummaries] = useState<SummaryListItem[]>([])
  const [recentVideos, setRecentVideos] = useState<VideoTask[]>([])
  useWarmCache<Stats>(CacheKeys.STATS,value=>{setStats(value);setLoading(false)})
  useWarmCache<SummaryListItem[]>(CacheKeys.RECENT_SUMMARIES,value=>{setSummaries(value);setLoading(false)})
  useWarmCache<VideoTask[]>(CacheKeys.RECENT_VIDEOS,value=>{setRecentVideos(value);setLoading(false)})
  const [loading, setLoading] = useState(true)
  usePageTiming('dashboard', !loading, CacheKeys.STATS)
  const [error, setError] = useState('')
  const [episodeUrl, setEpisodeUrl] = useState('')
  const [processing, setProcessing] = useState(false)
  const [contentUpdates, setContentUpdates] = useState<ContentUpdate[]>(() => getCache('content-updates') || [])
  useWarmCache<ContentUpdate[]>('content-updates',setContentUpdates)
  const [updatesError,setUpdatesError] = useState('')
  const [dismissingUpdates,setDismissingUpdates] = useState(false)
  const updatesReadVersion = useRef(0)
  const [checkingUpdates, setCheckingUpdates] = useState(false)

  const { jobs, updateJob, removeJob, videoTasks, setVideoTasks } = useStore()
  const { addToast } = useToast()

  async function handleCancelQueueItem(id: string, kind: 'podcast' | 'video') {
    try {
      if (kind === 'podcast') {
        await cancelJob(id)
        removeJob(id)
      } else {
        await cancelVideoTask(id)
        setVideoTasks(videoTasks.filter(t => t.id !== id))
      }
      addToast({ type: 'info', title: 'Cancelled', message: 'Task has been cancelled' })
    } catch (err) {
      addToast({ type: 'error', title: 'Cancel failed', message: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  const activeVideoJobs: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => VIDEO_QUEUE_STATUSES.has(t.status) && t.status !== 'success' && t.status !== 'failed')
      .map(t => ({
        job_id: t.id,
        status: t.status === 'saving' ? 'summarizing' : t.status,
        progress: t.progress,
        message: t.message || t.title || '',
        episode_title: t.title || (t.url ? (() => { try { return new URL(t.url).hostname + new URL(t.url).pathname.slice(0, 30) } catch { return t.url } })() : 'Video'),
      }))
  }, [videoTasks])

  const recentlyDoneVideos: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => (t.status === 'success' || t.status === 'failed') && !shouldDismissCompleted(t.id))
      .slice(0, 3)
      .map(t => ({
        job_id: t.id,
        status: t.status,
        progress: 100,
        message: t.status === 'success' ? 'Notes generated!' : (t.error || t.message || 'Failed'),
        episode_title: t.title || 'Video',
      }))
  }, [videoTasks])

  const allQueueItems = useMemo(() => {
    const activePodcasts = jobs
      .filter(j => j.status !== 'completed' && j.status !== 'failed' && j.status !== 'cancelled')
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const donePodcasts = jobs
      .filter(j => (j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled') && !shouldDismissCompleted(j.job_id))
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const videoJobs = activeVideoJobs.map(j => ({ ...j, _kind: 'video' as const }))
    const doneVideos = recentlyDoneVideos.slice(0, 2).map(j => ({ ...j, _kind: 'video' as const }))

    return [...activePodcasts, ...videoJobs, ...donePodcasts, ...doneVideos]
  }, [jobs, activeVideoJobs, recentlyDoneVideos])

  // Mark completed queue items as seen so they auto-dismiss on next load
  const queueSeenRef = useRef(false)
  useEffect(() => {
    const doneIds = [
      ...jobs.filter(j => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled').map(j => j.job_id),
      ...videoTasks.filter(t => t.status === 'success' || t.status === 'failed').map(t => t.id),
    ]
    if (doneIds.length > 0 && !queueSeenRef.current) {
      queueSeenRef.current = true
      markSeen(doneIds)
    }
  }, [jobs, videoTasks])

  useEffect(() => {
    loadData()
    void loadContentUpdates()
    const refresh = () => { if (!document.hidden) void loadContentUpdates() }
    const timer = window.setInterval(refresh,30000)
    window.addEventListener('focus',refresh)
    return () => { window.clearInterval(timer);window.removeEventListener('focus',refresh) }
  }, [])

  async function loadData() {
    const owner = getAccountId()
    setError('')
    const cachedStats = getCache<Stats>(CacheKeys.STATS)
    const cachedSummaries = getCache<SummaryListItem[]>(CacheKeys.RECENT_SUMMARIES)
    const cachedRecentVideos = getCache<VideoTask[]>(CacheKeys.RECENT_VIDEOS)

    if (cachedStats) setStats(cachedStats)
    if (cachedSummaries) setSummaries(cachedSummaries)
    if (cachedRecentVideos) setRecentVideos(cachedRecentVideos)
    if (cachedStats || cachedSummaries || cachedRecentVideos) setLoading(false)

    try {
      await Promise.all([
        fetchStats().then(data => { setStats(data); setCache(CacheKeys.STATS, data, owner); setLoading(false) }),
        fetchRecentSummaries().then(data => { setSummaries(data); setCache(CacheKeys.RECENT_SUMMARIES, data, owner); setLoading(false) }),
        fetchRecentVideoTasks().then(data => { setRecentVideos(data.tasks); setCache(CacheKeys.RECENT_VIDEOS, data.tasks, owner); setLoading(false) }),
      ])
    } catch (err) {
      console.error('Failed to load data:', err)
      setError('Cannot refresh the dashboard. Any saved content may be out of date.')
    } finally {
      setLoading(false)
    }
  }

  async function loadContentUpdates() {
    const version = ++updatesReadVersion.current
    const owner = getAccountId()
    try {
      const data = await fetchContentUpdates()
      if(owner !== getAccountId() || version !== updatesReadVersion.current) return
      setContentUpdates(data.items)
      setCache('content-updates',data.items,owner)
      setUpdatesError('')
    } catch {
      if(owner === getAccountId() && version === updatesReadVersion.current) setUpdatesError('Cannot refresh new content. Saved updates are shown.')
    }
  }

  async function dismissUpdates() {
    const keys = contentUpdates.map(item=>item.item_key)
    const owner = getAccountId()
    setDismissingUpdates(true)
    try {
      await dismissContentUpdates(keys)
      if(owner !== getAccountId()) return
      updatesReadVersion.current += 1
      // Keep discoveries arriving while the dismissal request was in flight.
      setContentUpdates(items=>{
        const next=items.filter(item=>!keys.includes(item.item_key))
        setCache('content-updates',next,owner)
        return next
      })
      void loadContentUpdates()
    } catch { addToast({type:'error',title:'Could not dismiss updates',message:'Please retry.'}) }
    finally { setDismissingUpdates(false) }
  }

  async function handleCheckUpdates() {
    setCheckingUpdates(true)
    try {
      const results = await Promise.allSettled([checkPodcastsForUpdates(),checkVideoChannelsForUpdates()])
      const episodes = results[0].status==='fulfilled' ? results[0].value.new_episodes : 0
      const videos = results[1].status==='fulfilled' ? results[1].value.new_videos : 0
      const failed=results.filter(result=>result.status==='rejected').length
      await loadContentUpdates()
      if(episodes || videos) {
        addToast({type:'success',title:'New content found',message:`${episodes} episode(s) + ${videos} video(s)`})
        void loadData()
      } else if(!failed) addToast({type:'info',title:'All caught up',message:'No new episodes or videos found'})
      if(failed) addToast({type:'error',title:'Some sources could not be checked',message:'Successful discoveries have been kept. Please retry the unavailable sources.'})
    } finally { setCheckingUpdates(false) }
  }

  async function handleProcess(e: React.FormEvent) {
    e.preventDefault()
    const url = episodeUrl.trim()
    if (!url) return

    setProcessing(true)
    try {
      const videoPlatform = detectVideoPlatform(url)
      if (videoPlatform) {
        const defaults = getVideoProcessingDefaults()
        const modelSettings = getUserModelSettings()
        await generateVideoNote({
          url,
          platform: videoPlatform,
          style: (defaults.style as string) || 'detailed',
          formats: (defaults.formats as string[]) || ['toc', 'summary', 'screenshot'],
          quality: (defaults.quality as string) || 'medium',
          video_quality: (defaults.video_quality as string) || '720',
          llm_model: modelSettings.llm_model,
        })
        setEpisodeUrl('')
        addToast({ type: 'success', title: 'Video processing started', message: 'Check the processing panel for progress' })
        loadData()
      } else {
        const result = await processEpisode(url)
        updateJob({
          job_id: result.job_id,
          status: 'pending',
          progress: 0,
          message: 'Starting...',
          episode_id: result.episode_id,
          episode_title: result.episode_title,
        })
        setEpisodeUrl('')
        addToast({ type: 'success', title: 'Processing started', message: 'Check the processing panel for progress' })
      }
    } catch (err) {
      console.error('Failed to start processing:', err)
      addToast({ type: 'error', title: 'Failed to start processing', message: err instanceof Error ? err.message : 'Unknown error' })
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  return (
    <div className="workspace-page dashboard-page space-y-6">
      {error && <LoadError message={error} onRetry={() => { void loadData() }} />}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="page-title text-2xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-gray-400">Continue reading and follow your processing tasks</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
        {contentUpdates.length>0 && <a href="#dashboard-new-content" className="flex items-center gap-1.5 rounded-lg bg-indigo-600/20 px-3 py-2 text-sm text-indigo-300"><Bell size={16}/><span>{contentUpdates.length}{contentUpdates.length===100?'+':''} new</span></a>}
        <button
          onClick={handleCheckUpdates}
          disabled={checkingUpdates}
          className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
          title="Check podcasts and video channels for new content"
        >
          <RefreshCw size={16} className={checkingUpdates ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">{checkingUpdates ? 'Checking...' : 'Check Updates'}</span>
        </button>
        </div>
      </div>

      {/* Stats — podcast + video combined */}
      {stats && (
        <div className="dashboard-stats grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3">
          <StatCard icon={Radio} label="Podcasts" value={stats.total_podcasts} color="text-indigo-500" />
          <StatCard icon={FileText} label="Episodes" value={stats.total_episodes} color="text-blue-500" />
          <StatCard icon={FileText} label="Transcripts" value={stats.total_transcripts} color="text-green-500" />
          <StatCard icon={MessageSquare} label="Summaries" value={stats.total_summaries} color="text-purple-500" />
          <StatCard icon={Users} label="Channels" value={stats.total_video_channels} color="text-orange-500" />
          <StatCard icon={Video} label="Videos" value={stats.total_videos} color="text-cyan-500" />
          <StatCard icon={CheckCircle} label="Completed" value={stats.completed_videos} color="text-emerald-500" />
        </div>
      )}

      {/* Quick process form */}
      <div id="dashboard-add-content" className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4">Add content</h2>
        <form onSubmit={handleProcess} className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <input
            type="text"
            value={episodeUrl}
            onChange={(e) => setEpisodeUrl(e.target.value)}
            aria-label="Podcast episode or video URL" placeholder="Paste podcast episode or video URL..."
            className="flex-1 px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
          />
          <button
            type="submit"
            disabled={processing || !episodeUrl.trim()}
            className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            {processing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
            Process
          </button>
        </form>
      </div>

      {/* Two-column: Recent summaries + Recent video notes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent podcast summaries */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Continue reading · Podcasts</h2>
            <Link
              to="/library?kind=podcast"
              className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
            >
              View all <ArrowRight size={16} />
            </Link>
          </div>
          {summaries.length === 0 ? (
            <div className="p-8 bg-dark-surface border border-dark-border rounded-xl text-center">
              <FileText className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">No summaries yet</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {summaries.slice(0, 4).map((summary) => (
                <SummaryCard key={summary.episode_id} summary={summary} />
              ))}
            </div>
          )}
        </div>

        {/* Recent video notes */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Continue reading · Videos</h2>
            <Link
              to="/library?kind=video"
              className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
            >
              View all <ArrowRight size={16} />
            </Link>
          </div>
          {recentVideos.length === 0 ? (
            <div className="p-8 bg-dark-surface border border-dark-border rounded-xl text-center">
              <Video className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">No video notes yet</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {recentVideos.slice(0, 4).map((task) => (
                <Link
                  key={task.id}
                  to={`/videos/${task.id}`}
                  onPointerEnter={() => prefetchVideoNote(task.id)}
                  onFocus={() => prefetchVideoNote(task.id)}
                  onTouchStart={() => prefetchVideoNote(task.id)}
                  className="flex gap-4 p-4 min-h-[104px] bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors"
                >
                  {task.thumbnail ? (
                    <CachedImage src={task.thumbnail} alt="" className="w-20 h-14 rounded object-cover flex-shrink-0 bg-dark-hover my-auto" />
                  ) : (
                    <div className="w-20 h-14 rounded bg-dark-hover flex items-center justify-center flex-shrink-0 my-auto">
                      <Video size={16} className="text-gray-600" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <h3 className="font-medium text-white line-clamp-2">
                      {task.title || (task.url ? (() => {
                        if (task.platform === 'local') {
                          const parts = task.url.split(/[\\/]/)
                          const filename = parts[parts.length - 1] || task.url
                          return filename.replace(/\.[^.]+$/, '')
                        }
                        try { return new URL(task.url).hostname.replace('www.', '') + new URL(task.url).pathname.replace(/\/$/, '').slice(0, 30) }
                        catch { return 'Untitled' }
                      })() : 'Untitled')}
                    </h3>
                    <div className="flex items-center gap-4 text-sm text-gray-400 mt-auto">
                      {task.channel && (
                        <span className="flex items-center gap-1.5 truncate">
                          {task.channel_avatar ? (
                            <CachedImage src={task.channel_avatar} alt="" className="w-4 h-4 rounded-full flex-shrink-0 bg-dark-hover" />
                          ) : (
                            <Video size={14} className="text-cyan-400 flex-shrink-0" />
                          )}
                          <span className="truncate">{task.channel}</span>
                        </span>
                      )}
                      {task.style && <span className="px-1.5 py-0.5 bg-purple-600/20 text-purple-400 rounded-full text-xs">{task.style}</span>}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Persistent source discoveries; dismissal only affects the displayed items. */}
      {updatesError && <div role="status" className="text-sm text-amber-300">{updatesError} <button className="underline" onClick={()=>void loadContentUpdates()}>Retry</button></div>}
      {contentUpdates.length > 0 && (
        <section id="dashboard-new-content" aria-label="New content" className="p-4 bg-indigo-900/30 border border-indigo-500/30 rounded-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 min-w-0">
              <Bell className="w-5 h-5 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div className="min-w-0">
                <h3 className="font-medium text-white mb-2">New content · {contentUpdates.filter(item=>item.kind==='podcast').length} episodes · {contentUpdates.filter(item=>item.kind==='video').length} videos</h3>
                <ul className="space-y-2">
                  {contentUpdates.slice(0,5).map(item=>(
                    <li key={item.item_key}><Link className="flex items-center gap-2 text-sm text-gray-300 hover:text-indigo-300" to={item.kind==='podcast' ? `/podcasts/${encodeURIComponent(item.source_id)}/episodes` : '/videos'}>
                      {item.kind==='podcast' ? <Radio size={15} className="shrink-0 text-indigo-400"/> : <Video size={15} className="shrink-0 text-violet-400"/>}
                      <span className="truncate">{item.source_title && <span className="text-indigo-300">{item.source_title}: </span>}{item.title || 'New video'}</span>
                    </Link></li>
                  ))}
                </ul>
                {contentUpdates.length>5 && <details className="mt-2 text-sm text-gray-400"><summary className="cursor-pointer">Show {contentUpdates.length-5} more</summary><ul className="mt-2 space-y-2">{contentUpdates.slice(5).map(item=><li key={item.item_key}><Link className="hover:text-indigo-300" to={item.kind==='podcast' ? `/podcasts/${encodeURIComponent(item.source_id)}/episodes` : '/videos'}>{item.source_title}: {item.title || 'New video'}</Link></li>)}</ul></details>}
              </div>
            </div>
            <button aria-label="Dismiss these updates" disabled={dismissingUpdates} onClick={()=>void dismissUpdates()} className="p-2 text-gray-400 hover:text-white disabled:opacity-50"><X size={16}/></button>
          </div>
        </section>
      )}

      {/* Processing jobs — podcast + video combined */}
      {allQueueItems.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Processing Queue</h2>
          <div className="space-y-3">
            {allQueueItems.map((item) => {
              const isVideo = item._kind === 'video'
              const isDone = item.status === 'completed' || item.status === 'success'
              const link = isDone
                ? isVideo ? `/videos/${item.job_id}` : item.episode_id ? `/viewer/${item.episode_id}` : undefined
                : undefined
              return (
                <ProcessingProgress
                  key={`${item._kind}-${item.job_id}`}
                  job={item}
                  link={link}
                  kind={item._kind}
                  onCancel={(id) => handleCancelQueueItem(id, item._kind)}
                />
              )
            })}
          </div>
        </div>
      )}




    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  color
}: {
  icon: typeof Radio
  label: string
  value: number
  color: string
}) {
  return (
    <div className="p-4 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-dark-hover ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xl font-bold text-white">{value}</p>
          <p className="text-xs text-gray-400">{label}</p>
        </div>
      </div>
    </div>
  )
}
