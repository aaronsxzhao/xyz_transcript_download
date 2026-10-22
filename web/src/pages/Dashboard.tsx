import {dismissedTasks} from '../lib/taskPreferences'
const taskAction=async(action:'cancelTask'|'retryTask'|'dismissTask',job:import('../lib/api').ProcessingJob,kind:'podcast'|'video')=>(await import('../lib/taskActions'))[action](job,kind)
import LoadError from '../components/LoadError'
import { getAccountId,getPreference,setPreference } from '../lib/preferences'
import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Radio, FileText, MessageSquare, Loader2, Plus, Bell, RefreshCw, X, Video, CheckCircle, Users } from 'lucide-react'
import { fetchStats, fetchRecentSummaries, processEpisode, fetchContentUpdates, dismissContentUpdates, type ContentUpdates, checkPodcastsForUpdates, checkVideoChannelsForUpdates, fetchRecentVideoTasks, generateVideoNote, getVideoProcessingDefaults, getUserModelSettings, type Stats, type SummaryListItem, type ProcessingJob, type VideoTask } from '../lib/api'
import { useStore } from '../lib/store'
import { useWarmCache, getCache, setCache, CacheKeys } from '../lib/cache'
import { useToast } from '../components/Toast'
import { markSeen, shouldDismissCompleted } from '../lib/seen'
import NoteCard from '../components/NoteCard'
import {useVerifiedReading} from '../lib/readingHistory'
import ProcessingProgress from '../components/ProcessingProgress'
import { usePageTiming } from '../lib/pageTiming'

const UPDATES_CACHE='content-updates:v2'
const DISMISSED_BEFORE='content_updates_dismissed_before'
// Keep database microseconds when filtering a response racing with dismissal.
const updateTime=(value:string)=>{
  const fraction=(value.match(/\.(\d+)/)?.[1]||'').padEnd(6,'0')
  return Date.parse(value.replace(/\.\d+/,'.'+fraction.slice(0,3)))*1000+Number(fraction.slice(3,6))
}
function unreadSnapshot(snapshot:ContentUpdates):ContentUpdates {
  const before=updateTime(getPreference(DISMISSED_BEFORE)||'')
  return Number.isFinite(before)?{...snapshot,items:snapshot.items.filter(item=>updateTime(item.created_at)>before)}:snapshot
}

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
  const {items:reading,status:readingStatus,retry:retryReading} = useVerifiedReading()
  const [recentReady,setRecentReady]=useState({podcasts:!!getCache(CacheKeys.RECENT_SUMMARIES),videos:!!getCache(CacheKeys.RECENT_VIDEOS)})
  const [stats, setStats] = useState<Stats | null>(null)
  const [summaries, setSummaries] = useState<SummaryListItem[]>([])
  const [recentVideos, setRecentVideos] = useState<VideoTask[]>([])
  useWarmCache<Stats>(CacheKeys.STATS,value=>{setStats(value);setLoading(false)})
  useWarmCache<SummaryListItem[]>(CacheKeys.RECENT_SUMMARIES,value=>{setSummaries(value);setRecentReady(previous=>({...previous,podcasts:true}));setLoading(false)})
  useWarmCache<VideoTask[]>(CacheKeys.RECENT_VIDEOS,value=>{setRecentVideos(value);setRecentReady(previous=>({...previous,videos:true}));setLoading(false)})
  const [loading, setLoading] = useState(true)
  usePageTiming('dashboard', !loading, CacheKeys.STATS)
  const [error, setError] = useState('')
  const [episodeUrl, setEpisodeUrl] = useState('')
  const [processing, setProcessing] = useState(false)
  const [updatesSnapshot,setUpdatesSnapshot]=useState<ContentUpdates>(()=>unreadSnapshot(getCache<ContentUpdates>(UPDATES_CACHE)||{items:[]}))
  const contentUpdates=updatesSnapshot.items
  useWarmCache<ContentUpdates>(UPDATES_CACHE,value=>setUpdatesSnapshot(unreadSnapshot(value)))
  const [updatesError,setUpdatesError] = useState('')
  const [dismissingUpdates,setDismissingUpdates] = useState(false)
  const updatesReadVersion = useRef(0)
  const dismissingRef=useRef(false)
  const [checkingUpdates, setCheckingUpdates] = useState(false)

  const { jobs, updateJob, videoTasks } = useStore()
  const { addToast } = useToast()

  const activeVideoJobs: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => VIDEO_QUEUE_STATUSES.has(t.status) && t.status !== 'success' && t.status !== 'failed')
      .map(t => ({
        job_id: t.id,
        status: t.status,
        progress: t.progress,
        started_at:t.started_at,
        message: t.message || t.title || '',
        episode_title: t.title || (t.url ? (() => { try { return new URL(t.url).hostname + new URL(t.url).pathname.slice(0, 30) } catch { return t.url } })() : 'Video'),
      }))
  }, [videoTasks])

  const recentlyDoneVideos: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => (t.status === 'success' || t.status === 'failed') && (t.status === 'failed' || !shouldDismissCompleted(t.id)))
      .slice(0, 3)
      .map(t => ({
        job_id: t.id,
        status: t.status,
        progress: 100,
        message: t.status === 'success' ? 'Notes generated!' : (t.error || t.message || 'Failed'),
        episode_title: t.title || 'Video',
      }))
  }, [videoTasks])

  const [dismissalRevision,setDismissalRevision]=useState(0)
  useEffect(()=>{const refresh=()=>setDismissalRevision(n=>n+1);window.addEventListener("xyz:tasks-dismissed",refresh);return()=>window.removeEventListener("xyz:tasks-dismissed",refresh)},[])
  const allQueueItems = useMemo(() => {
    const activePodcasts = jobs
      .filter(j => j.status !== 'completed' && j.status !== 'failed' && j.status !== 'cancelled')
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const donePodcasts = jobs
      .filter(j => (j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled') && (j.status === 'failed' || !shouldDismissCompleted(j.job_id)))
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const videoJobs = activeVideoJobs.map(j => ({ ...j, _kind: 'video' as const }))
    const doneVideos = recentlyDoneVideos.slice(0, 2).map(j => ({ ...j, _kind: 'video' as const }))

    const dismissed=dismissedTasks()
    return [...activePodcasts, ...videoJobs, ...donePodcasts, ...doneVideos].filter(row=>!['failed','success','completed','cancelled'].includes(row.status)||!dismissed.includes(row._kind+':'+row.job_id))
  }, [jobs, activeVideoJobs, recentlyDoneVideos,dismissalRevision])

  // Mark completed queue items as seen so they auto-dismiss on next load
  const queueSeenRef = useRef(false)
  useEffect(() => {
    const doneIds = [
      ...jobs.filter(j => j.status === 'completed').map(j => j.job_id),
      ...videoTasks.filter(t => t.status === 'success').map(t => t.id),
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
      const results=await Promise.allSettled([
        fetchStats().then(data => { setStats(data); setCache(CacheKeys.STATS, data, owner); setLoading(false) }),
        fetchRecentSummaries().then(data => { setSummaries(data);setRecentReady(previous=>({...previous,podcasts:true})); setCache(CacheKeys.RECENT_SUMMARIES, data, owner); setLoading(false) }),
        fetchRecentVideoTasks().then(data => { setRecentVideos(data.tasks);setRecentReady(previous=>({...previous,videos:true})); setCache(CacheKeys.RECENT_VIDEOS, data.tasks, owner); setLoading(false) }),
      ])
      if(results.some(result=>result.status==='rejected')) setError('Cannot refresh the dashboard. Any saved content may be out of date.')
    } catch (err) {
      console.error('Failed to load data:', err)
      setError('Cannot refresh the dashboard. Any saved content may be out of date.')
    } finally {
      setLoading(false)
      setRecentReady({podcasts:true,videos:true})
    }
  }

  async function loadContentUpdates() {
    if(dismissingRef.current) return
    const version = ++updatesReadVersion.current
    const owner = getAccountId()
    try {
      const data = await fetchContentUpdates()
      if(owner !== getAccountId() || version !== updatesReadVersion.current) return
      const next=unreadSnapshot(data)
      setUpdatesSnapshot(next)
      setCache(UPDATES_CACHE,next,owner)
      setUpdatesError('')
    } catch {
      if(owner === getAccountId() && version === updatesReadVersion.current) setUpdatesError('Cannot refresh new content. Saved updates are shown.')
    }
  }

  async function dismissUpdates() {
    if(dismissingRef.current) return
    const keys=contentUpdates.map(item=>item.item_key)
    const before=updatesSnapshot.dismiss_before
    const owner=getAccountId()
    dismissingRef.current=true
    updatesReadVersion.current++
    setDismissingUpdates(true)
    try {
      await dismissContentUpdates(keys,before)
      if(owner!==getAccountId()) return
      updatesReadVersion.current++
      if(before && updateTime(before)>updateTime(getPreference(DISMISSED_BEFORE)||'1970-01-01')) setPreference(DISMISSED_BEFORE,before)
      setUpdatesSnapshot(previous=>{
        const next=before?unreadSnapshot(previous):{...previous,items:previous.items.filter(item=>!keys.includes(item.item_key))}
        setCache(UPDATES_CACHE,next,owner)
        return next
      })
    } catch { addToast({type:'error',title:'Could not dismiss updates',message:'Please retry.'}) }
    finally { dismissingRef.current=false;setDismissingUpdates(false) }
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

      {/* Persistent source discoveries; closing acknowledges the unread snapshot. */}
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
            <button aria-label="Dismiss these updates" title="Dismiss all updates available at this refresh" aria-busy={dismissingUpdates} disabled={dismissingUpdates} onClick={()=>void dismissUpdates()} className="p-2 text-gray-400 hover:text-white disabled:opacity-50">{dismissingUpdates?<Loader2 size={16} className="animate-spin"/>:<X size={16}/>}</button>
          </div>
        </section>
      )}


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

      <section aria-label="Continue reading" className="space-y-3">
        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">Continue reading</h2><Link className="text-sm text-indigo-300" to="/library">Open Library →</Link></div>
        {reading.length ? <div className="collection-grid">{reading.slice(0,4).map((item,index)=><NoteCard key={`${item.kind}:${item.id}`} item={item} reading priority={index<2}/>)}</div>:readingStatus==='error'?<LoadError message="Reading history could not be verified. Your saved notes are still in Library." onRetry={retryReading}/>:<p className="text-sm text-gray-400" role="status">{readingStatus==='loading'?'Restoring reading history…':'Open a summary to start your reading history on this device.'}</p>}
      </section>
      {/* Recent additions are separate from actual reading history. */}
      <details className="dashboard-recent" open={reading.length===0}><summary className="text-sm text-gray-400 cursor-pointer">Recently added</summary>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
          <section><div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold">Recently added · Podcasts</h2><Link to="/library?kind=podcast" className="text-sm text-indigo-300">View all →</Link></div>
            <div className="grid gap-3">{summaries.slice(0,2).map((summary,index)=><NoteCard key={summary.episode_id} priority={index===0} item={{id:summary.episode_id,kind:'podcast',title:summary.title,source:summary.podcast_title,thumbnail:summary.podcast_cover,topics_count:summary.topics_count}}/>)}</div>
            {!summaries.length&&<p role="status" className="text-sm text-gray-400">{recentReady.podcasts?'No summaries yet':'Loading saved summaries…'}</p>}
          </section>
          <section><div className="flex justify-between items-center mb-4"><h2 className="text-lg font-semibold">Recently added · Videos</h2><Link to="/library?kind=video" className="text-sm text-indigo-300">View all →</Link></div>
            <div className="grid gap-3">{recentVideos.slice(0,2).map((task,index)=><NoteCard key={task.id} priority={index===0} item={{id:task.id,kind:'video',title:task.title||'Untitled video',source:task.channel||task.platform,thumbnail:task.thumbnail}}/>)}</div>
            {!recentVideos.length&&<p role="status" className="text-sm text-gray-400">{recentReady.videos?'No video notes yet':'Loading saved video notes…'}</p>}
          </section>
        </div>
      </details>

      {/* Processing jobs — podcast + video combined */}
      {allQueueItems.length > 0 && (
        <details open={allQueueItems.some(item=>!['completed','success','failed','cancelled'].includes(item.status))} className="dashboard-queue">
          <summary className="text-lg font-semibold text-white cursor-pointer">Processing Queue · {allQueueItems.length}</summary>
          <div className="space-y-3">
            {allQueueItems.map((item) => {
              const isVideo = item._kind === 'video'
              const source = isVideo ? videoTasks.find(task => task.id === item.job_id) : undefined
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
                  platform={source?.platform}
                  sourceUrl={source?.url}
                  createdAt={source?.created_at}
                  onCancel={() => taskAction('cancelTask',item,item._kind)}
                  onRetry={() => taskAction('retryTask',item,item._kind)}
                  onDismiss={() => taskAction('dismissTask',item,item._kind)}
                />
              )
            })}
          </div>
        </details>
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
