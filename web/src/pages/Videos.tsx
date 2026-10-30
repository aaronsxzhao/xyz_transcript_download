import {useOutsideInteraction} from '../lib/outsideInteraction'
import { videoFailureHint } from '../lib/videoFailure'
import {sourceAction,TaskProgress} from '../components/TaskStatus'
import ContentDates from '../components/ContentDates'
import CachedImage from '../components/CachedImage'
import { useWarmCache } from '../lib/cache'
import { useReadingPosition } from '../lib/reading'
import LoadError from '../components/LoadError'
import { getCache, setCache, CacheKeys } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { usePageTiming } from '../lib/pageTiming'
import { prefetchVideoNote } from '../lib/summaryPrefetch'
import { useCallback, useEffect, useState, useMemo, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Plus, ChevronUp, ChevronDown, Video, Search, Trash2, RefreshCw, RotateCcw, Square,
  CheckCircle, XCircle, Loader2, ArrowLeft, ExternalLink, Play, Sparkles,
} from 'lucide-react'
import {lazy} from 'react'
import {OptionalTool} from '../components/DeferredView'
const VideoNoteForm=lazy(()=>import('../components/video/VideoNoteForm'))
const SourceUpdateStatus=lazy(()=>import('../components/SourceUpdateStatus'))
const BilibiliFavorites=lazy(()=>import('../components/video/BilibiliFavorites'))
import PlatformIcon, { PLATFORM_COLORS } from '../components/PlatformIcon'
import { useStore, mergeVideoTaskPair, filterRemovedVideoTasks } from '../lib/store'
import { useToast } from '../components/Toast'
import { markSeen, isNewItem } from '../lib/seen'
import {
  fetchVideoChannels, fetchVideoTasksByChannel,
  deleteVideoTask, deleteVideoChannel, retryVideoTask, cancelVideoTask,
  checkVideoChannelsForUpdates,
  type VideoTask, type VideoChannelStat,
} from '../lib/api'

const PLATFORM_META: Record<string, { label: string }> = {
  bilibili: { label: 'Bilibili' },
  youtube: { label: 'YouTube' },
  douyin: { label: '抖音' },
  kuaishou: { label: '快手' },
  local: { label: 'Local' },
  twitter: { label: 'X / Twitter' },
  substack: { label: 'Substack' },
  web: { label: 'Web articles & media' },
}

type View = { type: 'platforms' } | { type: 'channels'; platform: string } | { type: 'videos'; platform: string; channel: string }

const TERMINAL_VIDEO_STATUSES = new Set(['success', 'failed', 'cancelled', 'discovered'])
const RECENT_TERMINAL_TASK_WINDOW_MS = 15000

function isActiveVideoStatus(status: string) {
  return !TERMINAL_VIDEO_STATUSES.has(status)
}

export default function Videos() {
  const { videoTasks, mergeVideoTasks, removeVideoTask } = useStore()
  const [formOpen, setFormOpen] = useState(()=>new URLSearchParams(location.search).get('add')==='local'||new URLSearchParams(location.search).has('import'))
  const [favoritesOpen,setFavoritesOpen]=useState(false)
  const [search, setSearch] = useState('')
  const [channelQuery, setChannelQuery] = useState('')
  const [channelStatus, setChannelStatus] = useState('')
  const [channelSort, setChannelSort] = useState('newest')
  const [channelCursor, setChannelCursor] = useState<string | null>(null)
  const [channelRefreshing, setChannelRefreshing] = useState(false)
  const channelRequest = useRef(0)
  const channelAbort = useRef<AbortController | null>(null)
  useEffect(() => { const t = setTimeout(() => setChannelQuery(search), 250); return () => clearTimeout(t) }, [search])
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const checkingRef = useRef(false)
  const [checkProgress, setCheckProgress] = useState<{scope:string;report:Awaited<ReturnType<typeof checkVideoChannelsForUpdates>>} | null>(null)
  const [updateResult, setUpdateResult] = useState<{scope:string;report:Awaited<ReturnType<typeof checkVideoChannelsForUpdates>>} | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToast } = useToast()

  // Channel list state (loaded once, lightweight)
  const [channels, setChannels] = useState<VideoChannelStat[]>(() => getCache(CacheKeys.VIDEO_CHANNELS) || [])
  const [channelsLoading, setChannelsLoading] = useState(() => !getCache(CacheKeys.VIDEO_CHANNELS))

  // Per-channel video state (loaded on demand when drilling into a channel)
  const [channelTasks, setChannelTasks] = useState<VideoTask[]>([])
  const [channelTasksLoading, setChannelTasksLoading] = useState(false)
  // Track which channel is currently loaded
  const loadedChannelRef = useRef<string>('')

  const view: View = useMemo(() => {
    const platform = searchParams.get('platform')
    const channel = searchParams.get('channel')
    if (platform && channel) return { type: 'videos', platform, channel }
    if (platform) return { type: 'channels', platform }
    return { type: 'platforms' }
  }, [searchParams])
  const updateReport = updateResult?.scope === JSON.stringify(view) ? updateResult.report : null


  const setView = useCallback((v: View) => {
    const params: Record<string, string> = {}
    if (v.type === 'channels') params.platform = v.platform
    else if (v.type === 'videos') { params.platform = v.platform; params.channel = v.channel }
    setSearchParams(params)
  }, [setSearchParams])

  // Load channel list (called on mount and after mutations)
  const loadChannels = useCallback(async () => {
    const owner = getAccountId()
    setError('')
    try {
      const data = await fetchVideoChannels()
      if (owner !== getAccountId()) return
      setChannels(data.channels)
      setCache(CacheKeys.VIDEO_CHANNELS, data.channels, owner)
    } catch (e) {
      console.error('Failed to load channels:', e)
      if (owner !== getAccountId()) return
      setError(e instanceof Error ? e.message : 'Cannot load your video channels. Please retry.')
    } finally {
      if (owner === getAccountId()) setChannelsLoading(false)
    }
  }, [])

  const [loadedChannelFilter,setLoadedChannelFilter] = useState('')
  const channelFilter = `${channelQuery}:${channelStatus}:${channelSort}`
  const channelCacheKey = (platform:string, channel:string) => CacheKeys.CHANNEL_VIDEOS(platform, channel) + ':' + channelFilter
  usePageTiming(view.type === 'videos' ? 'channel' : 'videos',
    view.type === 'videos' ? loadedChannelRef.current === `${view.platform}::${view.channel}` && !channelTasksLoading && loadedChannelFilter === channelFilter : !channelsLoading,
    view.type === 'videos' ? channelCacheKey(view.platform, view.channel) : CacheKeys.VIDEO_CHANNELS,
    !!error)
  useReadingPosition(view.type === 'videos' ? `channel:${view.platform}:${view.channel}:${channelFilter}` : 'video-channels', undefined, !channelTasksLoading && (view.type!=='videos'||loadedChannelFilter===channelFilter))
  useWarmCache<{tasks:VideoTask[];next_cursor:string|null}>(view.type==='videos'?channelCacheKey(view.platform,view.channel):CacheKeys.VIDEO_CHANNELS, value=>{if(view.type==='videos'&&value.tasks){setChannelTasks(filterRemovedVideoTasks(value.tasks));setChannelCursor(value.next_cursor);setLoadedChannelFilter(channelFilter);setChannelTasksLoading(false)}else if(view.type!=='videos'&&Array.isArray(value)){setChannels(value);setChannelsLoading(false)}})
  const loadChannelTasks = useCallback(async (platform: string, channel: string, options: { preserveExisting?: boolean; cursor?:string } = {}) => {
    const owner = getAccountId(), attempt = ++channelRequest.current
    channelAbort.current?.abort(); channelAbort.current = new AbortController()
    const key = `${platform}::${channel}`
    const cacheKey = channelCacheKey(platform, channel)
    loadedChannelRef.current = key
    setChannelRefreshing(true); setError('')
    try {
      const data = await fetchVideoTasksByChannel(platform, channel, {q:channelQuery,status:channelStatus,sort:channelSort,cursor:options.cursor,signal:channelAbort.current.signal})
      if (attempt !== channelRequest.current || owner !== getAccountId()) return
      setChannelTasks(previous => {
        const tasks = filterRemovedVideoTasks(options.cursor ? [...previous, ...data.tasks.filter(row => !previous.some(old => old.id === row.id))] : data.tasks)
        setCache(cacheKey, {tasks,next_cursor:data.next_cursor,at:Date.now()}, owner)
        return tasks
      })
      setChannelCursor(data.next_cursor);setLoadedChannelFilter(channelFilter); mergeVideoTasks(data.tasks)
    } catch (e) {
      if (attempt === channelRequest.current && owner === getAccountId()) setError(e instanceof Error ? e.message : 'Cannot load videos. Please retry.')
    } finally {
      if (attempt === channelRequest.current) {setChannelTasksLoading(false);setChannelRefreshing(false)}
    }
  }, [channelQuery,channelStatus,channelSort,mergeVideoTasks])

  // Initial load
  useEffect(() => {
    loadChannels()
  }, [loadChannels])

  useEffect(() => {
    if (view.type === 'videos') {
      const cached = getCache<{tasks:VideoTask[];next_cursor:string|null;at:number}>(channelCacheKey(view.platform,view.channel))
      const sameChannel = loadedChannelRef.current === `${view.platform}::${view.channel}`
      if (cached) {setChannelTasks(filterRemovedVideoTasks(cached.tasks));setChannelCursor(cached.next_cursor);setLoadedChannelFilter(channelFilter);setChannelTasksLoading(false)}
      else if (!sameChannel) {setChannelTasks([]);setChannelTasksLoading(true);setChannelCursor(null)}
      if (!cached || Date.now()-cached.at>60000) void loadChannelTasks(view.platform,view.channel)
      else {loadedChannelRef.current=`${view.platform}::${view.channel}`;setChannelRefreshing(false)}
    } else {setChannelTasks([]);loadedChannelRef.current=''}
    return () => {channelRequest.current++;channelAbort.current?.abort()}
  }, [view, loadChannelTasks])

  // Global progress reconciliation supplies active tasks even without a socket.

  // Periodically refresh channel stats
  useEffect(() => {
    if (view.type === 'videos') return
    const interval = setInterval(() => { if (document.visibilityState !== 'hidden') void loadChannels() }, 60000)
    return () => clearInterval(interval)
  }, [loadChannels, view.type])

  const currentViewStoreTasks = useMemo(() => {
    if (view.type !== 'videos') return [] as VideoTask[]
    return videoTasks.filter(t =>
      t.platform === view.platform &&
      (t.channel || 'Unknown Channel') === view.channel
    )
  }, [videoTasks, view])

  const activeCurrentViewTaskIds = useMemo(() => {
    return currentViewStoreTasks
      .filter(task => isActiveVideoStatus(task.status))
      .map(task => task.id)
      .sort()
  }, [currentViewStoreTasks])

  const previousActiveCurrentViewTaskIdsRef = useRef<string[]>([])
  useEffect(() => {
    if (view.type !== 'videos') {
      previousActiveCurrentViewTaskIdsRef.current = []
      return
    }

    const previousActiveIds = previousActiveCurrentViewTaskIdsRef.current
    const finishedTaskIds = previousActiveIds.filter(taskId =>
      !activeCurrentViewTaskIds.includes(taskId) &&
      currentViewStoreTasks.some(task => task.id === taskId && TERMINAL_VIDEO_STATUSES.has(task.status))
    )

    previousActiveCurrentViewTaskIdsRef.current = activeCurrentViewTaskIds

    if (finishedTaskIds.length > 0) {
      loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
      loadChannels()
    }
  }, [activeCurrentViewTaskIds, currentViewStoreTasks, view, loadChannelTasks, loadChannels])

  const seenMarkedRef = useRef(false)
  useEffect(() => {
    if (channelTasks.length > 0 && !seenMarkedRef.current) {
      seenMarkedRef.current = true
      markSeen(channelTasks.map(t => t.id))
    }
  }, [channelTasks])

  const runUpdateCheck = async (channelName?: string) => {
    if (checkingRef.current) return
    checkingRef.current = true
    setChecking(true);setUpdateResult(null);setCheckProgress(null)
    const scope = JSON.stringify(view)
    try {
      const opts = {platform:view.type !== 'platforms' ? view.platform : undefined,channel:channelName || (view.type === 'videos' ? view.channel : undefined)}
      const result = await checkVideoChannelsForUpdates(opts, report=>setCheckProgress({scope,report}))
      setUpdateResult({scope,report:result})
      const incomplete = result.channels_failed || result.interrupted
      addToast({
        type:result.new_videos ? (incomplete ? 'info' : 'success') : incomplete ? 'error' : 'info',
        title:result.new_videos ? (incomplete ? 'New items found · check incomplete' : 'New items found') : incomplete ? 'Update check incomplete' : result.channels_checked ? 'All caught up' : 'No update sources',
        message:result.interrupted || (incomplete ? `${result.new_videos} new items saved; ${result.channels_failed} sources unavailable. See source details below.` : result.message),
      })
      if (result.new_videos || result.interrupted) {
        loadChannels()
        if (view.type === 'videos') loadChannelTasks(view.platform,view.channel,{preserveExisting:true})
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      addToast({type:'error',title:'Check failed',message:err instanceof Error ? err.message : 'Unknown error'})
    } finally {
      checkingRef.current = false
      setChecking(false)
    }
  }
  const handleCheckUpdates = () => runUpdateCheck()
  const handleCheckChannelUpdates = (name:string) => runUpdateCheck(name)

  const handleDeleteChannel = async (channelName: string) => {
    try {
      const result = await deleteVideoChannel(channelName)
      addToast({ type: 'success', title: 'Channel deleted', message: result.message })
      loadChannels()
    } catch (err) {
      addToast({ type: 'error', title: 'Delete failed', message: err instanceof Error ? err.message : 'Unknown error' })
    }
  }


  const handleTaskCreated = (task: { taskId: string; title: string; url: string; platform: string; initialTask?: VideoTask | null }) => {
    if (task.initialTask) {
      useStore.getState().updateVideoTask(task.initialTask)
    } else {
      const isOptimisticLocalTask = task.platform === 'local'
      useStore.getState().updateVideoTask({
        id: task.taskId,
        client_pending:true,
        url: task.url || '',
        platform: task.platform || '',
        title: task.title || '',
        thumbnail: '',
        channel: isOptimisticLocalTask ? 'Local Uploads' : '',
        channel_url: '',
        channel_avatar: '',
        status: 'pending',
        progress: 0,
        message: 'Queued for processing...',
        markdown: '', transcript: null, style: '', model: '', formats: [],
        quality: '', extras: '', video_understanding: false, video_interval: 4,
        grid_cols: 3, grid_rows: 3, duration: 0, error: '',
        published_at: '', created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      })
    }
    const taskPlatform = task.initialTask?.platform || task.platform || ''
    const isLocalTask = taskPlatform === 'local'
    addToast({
      type: 'success',
      title: 'Video queued',
      message: task.title
        ? `${task.title} is queued for processing`
        : isLocalTask
          ? 'Your local video is queued for processing'
          : 'Your video is queued for processing',
    })
    setFormOpen(false)
    // A fast import may finish before any active event was observed.
    loadChannels()
    if(view.type==='videos')void loadChannelTasks(view.platform,view.channel,{preserveExisting:true})
  }

  const handleDelete = async (taskId: string) => {
    const title = channelTasks.find(task => task.id === taskId)?.title || 'this saved item'
    if (!window.confirm(`Delete “${title}”? This removes the saved item and cannot be undone.`)) return
    try {
      await deleteVideoTask(taskId)
      removeVideoTask(taskId)
      setChannelTasks(prev => prev.filter(t => t.id !== taskId))
      loadChannels()
    } catch (e) { addToast({ type: 'error', title: 'Could not delete video', message: e instanceof Error ? e.message : 'Please retry.' }) }
  }
  const handleRetry = async (taskId: string) => {
    try {
      await retryVideoTask(taskId)
      const task = channelTasks.find(t => t.id === taskId)
      addToast({ type: 'success', title: 'Request accepted', message: task?.title || 'Follow the current processing status below.' })
      if (view.type === 'videos') loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
    } catch (e) {
      console.error('Retry failed:', e)
      addToast({ type: 'error', title: 'Failed to start processing', message: e instanceof Error ? e.message : 'Unknown error' })
    }
  }
  const handleCancel = async (taskId: string) => {
    try {
      await cancelVideoTask(taskId)
      if (view.type === 'videos') loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
    } catch (e) { addToast({ type: 'error', title: 'Could not cancel processing', message: e instanceof Error ? e.message : 'Please retry.' }) }
  }

  // Merge in-progress store tasks into the channel task list so they show immediately,
  // and keep just-finished tasks visible until the server-backed refresh catches up.
  const mergedChannelTasks = useMemo(() => {
    if (view.type !== 'videos') return channelTasks
    const ids = new Set(channelTasks.map(t => t.id))
    const now = Date.now()
    const extra = currentViewStoreTasks.filter(task => {
      if (ids.has(task.id) || task.status === 'discovered') return false
      if (isActiveVideoStatus(task.status)) return true

      const updatedAt = Date.parse(task.updated_at || task.created_at || '') || 0
      return updatedAt > 0 && now - updatedAt <= RECENT_TERMINAL_TASK_WINDOW_MS
    })
    const base = extra.length === 0 ? channelTasks : [...extra, ...channelTasks]
    return base.map(row => {
      const fromStore = videoTasks.find(t => t.id === row.id)
      return fromStore ? mergeVideoTaskPair(fromStore, row) : row
    })
  }, [channelTasks, currentViewStoreTasks, view, videoTasks])

  // Server controls filtering/order across the whole channel, not only loaded rows.
  const sortedChannelTasks = useMemo(() => channelRefreshing || loadedChannelFilter !== channelFilter ? mergedChannelTasks.filter(t=>channelTasks.some(row=>row.id===t.id)) : mergedChannelTasks.filter(t =>
    (!channelStatus || t.status === channelStatus) && (!channelQuery || t.title.toLowerCase().includes(channelQuery.toLowerCase()))
  ).sort((a,b) => (channelSort === 'oldest' ? 1 : -1) * ((a.created_at || '').localeCompare(b.created_at || '') || a.id.localeCompare(b.id))), [mergedChannelTasks,channelTasks,channelRefreshing,channelStatus,channelQuery,channelSort,loadedChannelFilter,channelFilter])

  // Channels filtered by search (for channel/platform views)
  const filteredChannels = useMemo(() => {
    if (!search) return channels
    const q = search.toLowerCase()
    return channels.filter(c =>
      c.channel.toLowerCase().includes(q) ||
      c.platform.toLowerCase().includes(q)
    )
  }, [channels, search])

  // Platforms derived from channel list
  const platformStats = useMemo(() => {
    const stats: Record<string, { total: number; done: number }> = {}
    for (const c of filteredChannels) {
      const p = c.platform || 'other'
      if (!stats[p]) stats[p] = { total: 0, done: 0 }
      stats[p].total += c.total
      stats[p].done += c.done
    }
    return stats
  }, [filteredChannels])

  const sortedPlatforms = useMemo(() => {
    const order = ['bilibili', 'youtube', 'douyin', 'kuaishou', 'local']
    return Object.keys(platformStats).sort((a, b) =>
      (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
      (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
    )
  }, [platformStats])

  const platformChannels = useMemo(() => {
    if (view.type !== 'channels' && view.type !== 'videos') return []
    const platform = view.type === 'channels' ? view.platform : view.platform
    return filteredChannels.filter(c => c.platform === platform)
  }, [filteredChannels, view])

  const totalVideos = channels.reduce((s, c) => s + c.total, 0)

  return (
    <div className="workspace-page space-y-5">
      {error && <LoadError message={error} onRetry={() => { void loadChannels(); if (view.type === 'videos') void loadChannelTasks(view.platform, view.channel) }} />}
      {(checking || updateReport) && <OptionalTool fallback={null} errorFallback={<p role="status">{updateReport?.message}</p>}><SourceUpdateStatus progress={checking && checkProgress?.scope === JSON.stringify(view) ? checkProgress.report : null} report={updateReport}/></OptionalTool>}
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {view.type !== 'platforms' && (
            <button
              aria-label="Back to library"
              onClick={() => {
                if (view.type === 'videos') setView({ type: 'channels', platform: view.platform })
                else setView({ type: 'platforms' })
              }}
              className="p-1.5 text-gray-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={18} />
            </button>
          )}
          <div>
            <h1 className="page-title text-xl md:text-2xl font-bold text-white">
              {view.type === 'platforms' && 'Videos & articles'}
              {view.type === 'channels' && (PLATFORM_META[view.platform]?.label || view.platform)}
              {view.type === 'videos' && view.channel}
            </h1>
            <p className="text-sm text-gray-400">
              {view.type === 'platforms' && `${totalVideos} saved item${totalVideos !== 1 ? 's' : ''}`}
              {view.type === 'channels' && `${platformChannels.length} channel${platformChannels.length !== 1 ? 's' : ''}`}
              {view.type === 'videos' && (channelTasksLoading ? 'Loading...' : `${sortedChannelTasks.length} videos`)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {(view.type==='platforms'||view.platform==='bilibili')&&<button onClick={()=>setFavoritesOpen(value=>!value)} aria-expanded={favoritesOpen} className="rounded-lg border border-dark-border px-3 py-2 text-sm">Bilibili favorites</button>}
          {(view.type==='platforms'||['youtube','bilibili','douyin','twitter','substack'].includes(view.platform))&&<button
            onClick={handleCheckUpdates}
            disabled={checking}
            aria-label="Check source updates"
            className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
            title={
              view.type === 'videos' ? `Check ${view.channel} for new content`
                : view.type === 'channels' ? `Check ${PLATFORM_META[view.platform]?.label || view.platform} sources for new content`
                : 'Check all sources for new content'
            }
          >
            <RefreshCw size={16} className={checking ? 'animate-spin' : ''} />
            <span>{checking ? 'Checking...' : 'Check Updates'}</span>
          </button>}
          <button onPointerEnter={()=>void import('../components/video/VideoNoteForm').catch(()=>{})} onFocus={()=>void import('../components/video/VideoNoteForm').catch(()=>{})} onClick={() => setFormOpen(!formOpen)}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors">
            <Plus size={16} /> Add content
          </button>
        </div>
      </div>

      {view.type === 'videos' && <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Channel video status" value={channelStatus} onChange={e=>setChannelStatus(e.target.value)} className="bg-dark-surface p-2 rounded"><option value="">All statuses</option><option value="success">Ready to read</option><option value="discovered">Not processed</option><option value="failed">Needs attention</option><option value="pending">Queued</option></select>
        <select aria-label="Channel video order" value={channelSort} onChange={e=>setChannelSort(e.target.value)} className="bg-dark-surface p-2 rounded"><option value="newest">Newest added</option><option value="oldest">Oldest added</option></select>
        <span role="status" className="text-sm text-gray-400">{channelRefreshing || search !== channelQuery ? 'Updating results…' : `${sortedChannelTasks.length} videos loaded`}</span>
      </div>}
      {/* New note form */}
      {formOpen && (
        <div className="video-import-panel bg-dark-surface rounded-xl border border-dark-border overflow-hidden">
          <div className="flex items-center justify-between px-4 pt-3 pb-0">
            <h3 className="text-sm font-semibold text-white">Add video, article or social content</h3>
            <button aria-label="Close new video note form" onClick={() => setFormOpen(false)} className="p-1 text-gray-500 hover:text-white transition-colors">
              <ChevronUp size={16} />
            </button>
          </div>
          <div className="px-4 pb-4 pt-2 ">
            <OptionalTool fallback={<p role="status">Loading video tools…</p>}><VideoNoteForm initialUrl={searchParams.get('import') || ''} onTaskCreated={handleTaskCreated} hideTitle /></OptionalTool>
          </div>
        </div>
      )}

      {favoritesOpen&&<OptionalTool fallback={<p role="status">Loading favorites tools…</p>}><BilibiliFavorites onImported={()=>void loadChannels()}/></OptionalTool>}
      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-gray-500" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)}
          aria-label={view.type === 'videos' ? 'Search videos' : 'Search channels'}
          placeholder={view.type === 'videos' ? 'Search videos...' : 'Search channels...'}
          className="w-full pl-9 pr-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500" />
      </div>

      {/* Horizontal platform quick-select (always visible) */}
      {view.type !== 'videos' && sortedPlatforms.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setView({ type: 'platforms' })}
            className={`flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
              view.type === 'platforms'
                ? 'bg-indigo-600 text-white'
                : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
            }`}
          >
            All ({totalVideos})
          </button>
          {sortedPlatforms.map(p => {
            const meta = PLATFORM_META[p] || { label: p }
            const stats = platformStats[p]
            const isActive = view.type === 'channels' && view.platform === p
            return (
              <button
                key={p}
                onClick={() => setView({ type: 'channels', platform: p })}
                className={`flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
                }`}
              >
                <PlatformIcon platform={p} size={15} className={isActive ? 'text-white' : PLATFORM_COLORS[p] || 'text-gray-400'} />
                {meta.label}
                <span className="text-xs">({stats.total})</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Content based on view */}
      {channelsLoading && view.type === 'platforms' ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
        </div>
      ) : channels.length === 0 && view.type === 'platforms' ? (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No video notes yet</p>
          <p className="text-gray-500">Create a new video note to get started</p>
        </div>
      ) : view.type === 'platforms' ? (
        /* Platform overview */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedPlatforms.map(p => {
            const meta = PLATFORM_META[p] || { label: p }
            const stats = platformStats[p]
            const platformChCount = filteredChannels.filter(c => c.platform === p).length
            return (
              <button
                key={p}
                onClick={() => setView({ type: 'channels', platform: p })}
                className="platform-overview-card block w-full min-w-0 p-5 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors text-left"
              >
                <div className="flex items-center gap-3 mb-3">
                  <PlatformIcon platform={p} size={28} className={PLATFORM_COLORS[p] || 'text-gray-400'} />
                  <h3 className="text-lg font-semibold text-white whitespace-nowrap">{meta.label}</h3>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-400">
                  <span>{platformChCount} channel{platformChCount !== 1 ? 's' : ''}</span>
                  <span>{stats.done}/{stats.total} completed</span>
                </div>
              </button>
            )
          })}
        </div>
      ) : view.type === 'channels' ? (
        /* Channel list for selected platform */
        <ChannelList
          channels={platformChannels}
          checkingUpdates={checking}
          onSelectChannel={(ch) => setView({ type: 'videos', platform: view.platform, channel: ch })}
          onDeleteChannel={handleDeleteChannel}
          onCheckUpdates={['youtube','bilibili','douyin','twitter','substack'].includes(view.platform) ? handleCheckChannelUpdates : undefined}
        />
      ) : (
        /* Video list for selected channel */
        channelTasksLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
          </div>
        ) : (
          <><VideoList
            videos={sortedChannelTasks}
            onDelete={handleDelete}
            onRetry={handleRetry}
            onCancel={handleCancel}
          />{channelCursor && <button disabled={channelRefreshing || search !== channelQuery || loadedChannelFilter !== channelFilter} className="block mx-auto mt-4 px-4 py-2 bg-dark-surface rounded" onClick={()=>void loadChannelTasks(view.platform,view.channel,{cursor:channelCursor})}>{channelRefreshing ? 'Loading videos…' : 'Show more videos'}</button>}</>
        )
      )}
    </div>
  )
}


function ChannelList({ channels, onSelectChannel, onDeleteChannel, onCheckUpdates, checkingUpdates = false }: {
  channels: VideoChannelStat[]
  onSelectChannel: (ch: string) => void
  onDeleteChannel?: (ch: string) => Promise<void> | void
  onCheckUpdates?: (ch: string) => Promise<void>
  checkingUpdates?: boolean
}) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [refreshing, setRefreshing] = useState<string | null>(null)

  if (channels.length === 0) {
    return (
      <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
        <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <p className="text-xl text-gray-400 mb-2">No channels found</p>
        <p className="text-gray-500">Process some videos to see channels here</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {channels.map((ch,index) => {
        const imgSrc = ch.channel_avatar || ch.thumbnail
        return (
          <div
            key={ch.channel}
            className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
          >
            <div className="collection-row">
              <Link className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0" to={'/videos?'+new URLSearchParams({platform:ch.platform,channel:ch.channel})}>
                {imgSrc ? (
                  <CachedImage priority={index<3} src={imgSrc} alt="" className={`w-14 h-14 md:w-20 md:h-20 flex-shrink-0 bg-dark-hover object-cover ${ch.channel_avatar ? 'rounded-full' : 'rounded-lg'}`} />
                ) : (
                  <div className="w-14 h-14 md:w-20 md:h-20 rounded-full bg-dark-hover flex items-center justify-center flex-shrink-0">
                    <Video className="w-6 h-6 md:w-8 md:h-8 text-gray-600" />
                  </div>
                )}

                <div className="flex-1 min-w-0">
                  <h3 className="text-base md:text-lg font-semibold text-white mb-1 line-clamp-2">
                    {ch.channel}
                  </h3>
                  <p className="text-sm text-indigo-400 mt-1 md:mt-2">
                    {ch.done > 0
                      ? `${ch.done} / ${ch.total} completed`
                      : `${ch.total} video${ch.total !== 1 ? 's' : ''}`
                    }
                  </p>
                </div>
              </Link>

              <div className="channel-actions collection-actions">
                <button
                  onClick={() => onSelectChannel(ch.channel)}
                  aria-label={`Open videos from ${ch.channel}`}
                  className="ui-button ui-button-icon-mobile"
                >
                  <Video size={16} />
                  <span className="hidden sm:inline">Videos</span>
                </button>
                {ch.channel_url && (
                  <a
                    href={ch.channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ui-button ui-button-icon"
                    title="Open channel page"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
                {onCheckUpdates && ch.channel_url && (
                  <button
                    onClick={async () => {
                      setRefreshing(ch.channel)
                      try { await onCheckUpdates(ch.channel) } finally { setRefreshing(null) }
                    }}
                    disabled={checkingUpdates || refreshing !== null} aria-busy={refreshing === ch.channel}
                    className="ui-button ui-button-icon disabled:opacity-50"
                    title="Check for new content"
                    aria-label={`Check updates for ${ch.channel}`}
                  >
                    <RefreshCw size={16} className={refreshing === ch.channel ? 'animate-spin' : ''} />
                  </button>
                )}
                {onDeleteChannel && (
                  confirmDelete === ch.channel ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={async () => {
                          setDeleting(true)
                          try { await onDeleteChannel(ch.channel) } finally { setDeleting(false); setConfirmDelete(null) }
                        }}
                        disabled={deleting} aria-busy={deleting}
                        className="ui-button ui-button-danger"
                      >
                        {deleting ? 'Deleting...' : 'Confirm'}
                      </button>
                      <button
                        disabled={deleting}
                        onClick={() => setConfirmDelete(null)}
                        className="ui-button"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      disabled={deleting}
                      onClick={() => setConfirmDelete(ch.channel)}
                      className="ui-button ui-button-icon ui-button-danger"
                      title="Delete channel and all its videos"
                    >
                      <Trash2 size={16} />
                    </button>
                  )
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}


function getDisplayTitle(task: VideoTask): string {
  if (task.title && task.title !== 'Untitled') return task.title
  if (task.url) {
    if (task.platform === 'local') {
      const parts = task.url.split(/[\/\\]/)
      const filename = parts[parts.length - 1] || task.url
      return filename.replace(/\.[^.]+$/, '') || filename
    }
    try {
      const u = new URL(task.url)
      const host = u.hostname.replace('www.', '')
      const path = u.pathname.replace(/\/$/, '')
      const shortPath = path.length > 40 ? '...' + path.slice(-37) : path
      return `${host}${shortPath}`
    } catch {
      return task.url.length > 60 ? task.url.slice(0, 57) + '...' : task.url
    }
  }
  return 'Untitled'
}


function VideoList({ videos, onDelete, onRetry, onCancel }: {
  videos: VideoTask[]
  onDelete: (id: string) => Promise<void>
  onRetry: (id: string) => Promise<void>
  onCancel: (id: string) => Promise<void>
}) {
  const navigate = useNavigate()
  const list = useRef<HTMLDivElement>(null)
  useOutsideInteraction(target => {
    for (const menu of list.current?.querySelectorAll<HTMLDetailsElement>('.task-more[open]') || []) {
      if (!menu.contains(target)) menu.open = false
    }
  })
  const activeActions = useRef(new Set<string>())
  const [pending, setPending] = useState(new Set<string>())
  const runAction = async (id:string, action:(id:string)=>Promise<void>) => {
    if (activeActions.current.has(id)) return
    activeActions.current.add(id); setPending(new Set(activeActions.current))
    try { await action(id) } finally { activeActions.current.delete(id); setPending(new Set(activeActions.current)) }
  }
  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    return `${m} min`
  }

  const isProcessing = (status: string) =>
    !['success', 'failed', 'cancelled', 'discovered'].includes(status)

  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())
  const toggleError = (id: string) => {
    setExpandedErrors(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  if (videos.length === 0) {
    return (
      <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
        <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <p className="text-xl text-gray-400 mb-2">No videos in this channel</p>
        <p className="text-gray-500">Process some videos to see them here</p>
      </div>
    )
  }

  return (
    <div ref={list} className="space-y-3 video-task-list">
      {videos.map((task,index) => {
        const isFailed = task.status === 'failed'
        const errorMsg = task.message && task.message !== 'Failed' ? task.message : task.error || ''
        const hint = isFailed ? videoFailureHint(task) : null
        const displayTitle = getDisplayTitle(task)

        const isClickable = task.status === 'success'
        return (
        <div
          key={task.id}
          onClick={isClickable ? () => navigate(`/videos/${task.id}`) : undefined}
          onPointerEnter={isClickable ? () => prefetchVideoNote(task.id) : undefined}
          onTouchStart={isClickable ? () => prefetchVideoNote(task.id) : undefined}
          className={`p-3 md:p-4 bg-dark-surface border rounded-xl transition-colors ${
            isFailed ? 'border-red-500/30 hover:border-red-500/50' : 'border-dark-border hover:border-dark-hover'
          } ${isClickable ? 'cursor-pointer' : ''}`}
        >
          <div className="video-task-content flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
            {task.thumbnail ? (
              <CachedImage priority={index<3} src={task.thumbnail} alt="" fit="contain" className="video-thumbnail w-full sm:w-40 md:w-48 h-24 sm:h-24 md:h-28 rounded-lg object-cover flex-shrink-0 bg-dark-hover" />
            ) : (
              <div className={`video-thumbnail hidden sm:flex w-40 md:w-48 h-24 md:h-28 rounded-lg items-center justify-center flex-shrink-0 ${
                isFailed ? 'bg-red-500/10' : 'bg-dark-hover'
              }`}>
                {isFailed ? (
                  <XCircle className="w-8 h-8 text-red-500/50" />
                ) : (
                  <Video className="w-8 h-8 text-gray-600" />
                )}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-white mb-1 line-clamp-2 text-sm md:text-base">
                {displayTitle}
              </h3>

              {(!task.title || task.title === 'Untitled') && task.url && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 mb-1 truncate"
                >
                  <ExternalLink size={10} className="flex-shrink-0" />
                  <span className="truncate">{task.url}</span>
                </a>
              )}

              <div className="flex flex-wrap items-center gap-2 md:gap-4 text-xs md:text-sm text-gray-400">
                <ContentDates published={task.published_at} imported={task.created_at} local={task.platform === "local"} compact />
                {task.duration > 0 && (
                  <span>{formatDuration(task.duration)}</span>
                )}

                {task.status === 'success' && (
                  <span className="flex items-center gap-1 text-green-500">
                    <CheckCircle size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Completed</span>
                  </span>
                )}
                {task.status === 'failed' && (
                  <button
                    onClick={() => toggleError(task.id)}
                    className="flex items-center gap-1 text-red-300 hover:text-red-200 transition-colors"
                  >
                    <XCircle size={12} className="md:w-3.5 md:h-3.5" />
                    Failed
                    <ChevronDown size={12} className={`transition-transform ${expandedErrors.has(task.id) ? 'rotate-180' : ''}`} />
                  </button>
                )}
                {task.status === 'cancelled' && (
                  <span className="flex items-center gap-1 text-orange-400">
                    <Square size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Cancelled</span>
                  </span>
                )}
                {['discovered', 'pending'].includes(task.status) && isNewItem(task.id) && (
                  <span className="flex items-center gap-1 text-cyan-400">
                    <Sparkles size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Newly Added</span>
                  </span>
                )}
              </div>

              {isFailed && errorMsg && (
                <div className="mt-2">
                  <p className={`text-xs text-red-300 ${expandedErrors.has(task.id) ? '' : 'line-clamp-1'}`}>
                    {errorMsg}
                  </p>
                  {hint && (
                    <p className="mt-1.5 text-xs text-amber-400/80 flex items-start gap-1.5">
                      <span className="flex-shrink-0 mt-0.5">💡</span>
                      <span>{hint}</span>
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="collection-actions" onClick={e => e.stopPropagation()}>
              {pending.has(task.id) && <span role="status" className="text-xs text-indigo-300">Submitting…</span>}
              {(() => {
                if (task.status === 'success') {
                  return (
                    <>
                      <Link
                        to={`/videos/${task.id}`}
                        onFocus={() => prefetchVideoNote(task.id)}
                        className="ui-button ui-button-primary"
                      >
                        <CheckCircle size={16} />
                        View
                      </Link>
                    </>
                  )
                }

                if (task.status === 'discovered') {
                  return (
                    <button
                      disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                      className="ui-button"
                      title="Start processing this video"
                    >
                      <Play size={16} />
                      Process
                    </button>
                  )
                }

                if (isProcessing(task.status)) {
                  return <div className="collection-task"><TaskProgress status={task.status} progress={task.progress} startedAt={task.started_at} message={task.message} compact/></div>
                }

                if(sourceAction(errorMsg))return <Link className="ui-button" to="/settings">Check source access</Link>
                return (
                  <button
                    disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                    className="ui-button"
                  >
                    <RotateCcw size={16} />
                    Retry
                  </button>
                )
              })()}

              {task.url && task.platform !== 'local' && !isProcessing(task.status) && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ui-button ui-button-icon"
                  title="Open original source" aria-label={`Open original source for ${displayTitle}`}
                >
                  <ExternalLink size={16} />
                </a>
              )}

              {!isProcessing(task.status) && (
                <details className="task-more" onKeyDown={event => {
                  if (event.key === 'Escape') {
                    event.currentTarget.open = false
                    event.currentTarget.querySelector('summary')?.focus()
                  }
                }}>
                  <summary className="ui-button" aria-label={`More actions for ${displayTitle}`}>More</summary>
                  <div>
                    {task.status === 'success' && (
                      <button
                        disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                        className="ui-button"
                        title="Re-process video" aria-label={`Re-process ${displayTitle}`}
                      >
                        <RefreshCw size={16} /><span>Re-Process</span>
                      </button>
                    )}
                    <button
                      disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onDelete)}
                      className="ui-button ui-button-danger"
                      title="Delete video"
                    >
                      <Trash2 size={16} /><span>Delete video</span>
                    </button>
                  </div>
                </details>
              )}

              {isProcessing(task.status) && task.status !== 'cancelling' && (
                <button
                  disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onCancel)}
                  className="ui-button ui-button-icon"
                  title="Cancel processing"
                >
                  <Square size={16} className="fill-current" />
                </button>
              )}
            </div>
          </div>
        </div>
        )
      })}
    </div>
  )
}
