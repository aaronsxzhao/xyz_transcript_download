import { useCallback, useEffect, useState, useMemo, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Plus, ChevronUp, ChevronDown, Video, Search, Trash2, RefreshCw, RotateCcw, Square,
  CheckCircle, XCircle, Clock, Loader2, ArrowLeft, ExternalLink, Play, Sparkles,
} from 'lucide-react'
import VideoNoteForm from '../components/video/VideoNoteForm'
import PlatformIcon, { PLATFORM_COLORS } from '../components/PlatformIcon'
import { useStore } from '../lib/store'
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
}

type View = { type: 'platforms' } | { type: 'channels'; platform: string } | { type: 'videos'; platform: string; channel: string }

export default function Videos() {
  const { videoTasks, mergeVideoTasks, removeVideoTask } = useStore()
  const [formOpen, setFormOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [checking, setChecking] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const { addToast } = useToast()

  // Channel list state (loaded once, lightweight)
  const [channels, setChannels] = useState<VideoChannelStat[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)

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

  const setView = useCallback((v: View) => {
    const params: Record<string, string> = {}
    if (v.type === 'channels') params.platform = v.platform
    else if (v.type === 'videos') { params.platform = v.platform; params.channel = v.channel }
    setSearchParams(params, { replace: true })
  }, [setSearchParams])

  // Load channel list (called on mount and after mutations)
  const loadChannels = useCallback(async () => {
    try {
      const data = await fetchVideoChannels()
      setChannels(data.channels)
    } catch (e) {
      console.error('Failed to load channels:', e)
    } finally {
      setChannelsLoading(false)
    }
  }, [])

  // Load tasks for the currently viewed channel
  const loadChannelTasks = useCallback(async (
    platform: string,
    channel: string,
    options: { preserveExisting?: boolean } = {},
  ) => {
    const key = `${platform}::${channel}`
    const preserveExisting = options.preserveExisting === true
    if (!preserveExisting) {
      if (loadedChannelRef.current !== key) {
        setChannelTasks([])
      }
      setChannelTasksLoading(true)
    }
    loadedChannelRef.current = key
    try {
      const data = await fetchVideoTasksByChannel(platform, channel)
      // Only apply if still viewing the same channel
      if (loadedChannelRef.current === key) {
        setChannelTasks(data.tasks)
        // Also push into store so active-task polling stays in sync
        mergeVideoTasks(data.tasks)
      }
    } catch (e) {
      console.error('Failed to load channel tasks:', e)
    } finally {
      if (!preserveExisting && loadedChannelRef.current === key) {
        setChannelTasksLoading(false)
      }
    }
  }, [mergeVideoTasks])

  // Initial load
  useEffect(() => {
    loadChannels()
  }, [loadChannels])

  // When view changes to a specific channel, fetch its tasks
  useEffect(() => {
    if (view.type === 'videos') {
      loadChannelTasks(view.platform, view.channel)
    } else {
      // Clear channel tasks when navigating away
      setChannelTasks([])
      loadedChannelRef.current = ''
    }
  }, [view, loadChannelTasks])

  // Poll active tasks from store (for in-progress processing)
  const hasActiveTasks = videoTasks.some(t =>
    !['success', 'failed', 'cancelled', 'discovered'].includes(t.status)
  )
  useEffect(() => {
    if (!hasActiveTasks) return
    // When there are active tasks in a channel view, re-fetch that channel periodically
    if (view.type !== 'videos') return
    const interval = setInterval(() => {
      loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
    }, 5000)
    return () => clearInterval(interval)
  }, [hasActiveTasks, view, loadChannelTasks])

  // Periodically refresh channel stats
  useEffect(() => {
    const interval = setInterval(loadChannels, hasActiveTasks ? 10000 : 60000)
    return () => clearInterval(interval)
  }, [loadChannels, hasActiveTasks])

  const seenMarkedRef = useRef(false)
  useEffect(() => {
    if (channelTasks.length > 0 && !seenMarkedRef.current) {
      seenMarkedRef.current = true
      markSeen(channelTasks.map(t => t.id))
    }
  }, [channelTasks])

  const handleCheckUpdates = async () => {
    setChecking(true)
    try {
      const opts: { channel?: string; platform?: string } = {}
      if (view.type === 'videos') opts.channel = view.channel
      else if (view.type === 'channels') opts.platform = view.platform

      const result = await checkVideoChannelsForUpdates(opts)
      if (result.new_videos > 0) {
        addToast({ type: 'success', title: 'New videos found', message: `Found ${result.new_videos} new video(s) from ${result.channels_checked} channel(s)` })
        loadChannels()
        if (view.type === 'videos') loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
      } else {
        const scope = view.type === 'videos' ? view.channel
          : view.type === 'channels' ? (PLATFORM_META[view.platform]?.label || view.platform)
          : 'all channels'
        addToast({ type: 'info', title: 'All caught up', message: `No new videos from ${scope}` })
      }
    } catch (err) {
      console.error('Failed to check for updates:', err)
      addToast({ type: 'error', title: 'Check failed', message: err instanceof Error ? err.message : 'Unknown error' })
    } finally {
      setChecking(false)
    }
  }

  const handleDeleteChannel = async (channelName: string) => {
    try {
      const result = await deleteVideoChannel(channelName)
      addToast({ type: 'success', title: 'Channel deleted', message: result.message })
      loadChannels()
    } catch (err) {
      addToast({ type: 'error', title: 'Delete failed', message: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  const handleCheckChannelUpdates = async (channelName: string) => {
    try {
      const result = await checkVideoChannelsForUpdates({ channel: channelName })
      if (result.new_videos > 0) {
        addToast({ type: 'success', title: 'New videos found', message: `Found ${result.new_videos} new video(s) from ${channelName}` })
        loadChannels()
      if (view.type === 'videos' && view.channel === channelName) loadChannelTasks(view.platform, view.channel, { preserveExisting: true })
      } else {
        addToast({ type: 'info', title: 'All caught up', message: `No new videos from ${channelName}` })
      }
    } catch (err) {
      addToast({ type: 'error', title: 'Check failed', message: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  const handleTaskCreated = (task: { taskId: string; title: string; url: string; platform: string }) => {
    useStore.getState().updateVideoTask({
      id: task.taskId,
      url: task.url || '',
      platform: task.platform || '',
      title: task.title || '',
      thumbnail: '',
      channel: task.platform === 'local' ? 'Local Uploads' : '',
      channel_url: '',
      channel_avatar: '',
      status: 'pending',
      progress: 0,
      message: 'Upload complete. Queued for processing...',
      markdown: '', transcript: null, style: '', model: '', formats: [],
      quality: '', extras: '', video_understanding: false, video_interval: 4,
      grid_cols: 3, grid_rows: 3, duration: 0, error: '',
      published_at: '', created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    })
    addToast({
      type: 'success',
      title: 'Video queued',
      message: task.title ? `${task.title} is now processing` : 'Your local video is now processing',
    })
    setFormOpen(false)
    // Refresh channel list so new channel/count appears
    loadChannels()
  }

  const handleDelete = async (taskId: string) => {
    try {
      await deleteVideoTask(taskId)
      removeVideoTask(taskId)
      setChannelTasks(prev => prev.filter(t => t.id !== taskId))
      loadChannels()
    } catch (e) { console.error('Delete failed:', e) }
  }
  const handleRetry = async (taskId: string) => {
    try {
      await retryVideoTask(taskId)
      const task = channelTasks.find(t => t.id === taskId)
      addToast({ type: 'success', title: 'Processing started', message: task?.title || 'Video processing started' })
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
    } catch (e) { console.error('Cancel failed:', e) }
  }

  // Merge in-progress store tasks into the channel task list so they show immediately
  const mergedChannelTasks = useMemo(() => {
    if (view.type !== 'videos') return channelTasks
    const activePlatformChannel = videoTasks.filter(t =>
      t.platform === view.platform &&
      (t.channel || 'Unknown Channel') === view.channel &&
      !['success', 'failed', 'cancelled', 'discovered'].includes(t.status)
    )
    if (activePlatformChannel.length === 0) return channelTasks
    const ids = new Set(channelTasks.map(t => t.id))
    const extra = activePlatformChannel.filter(t => !ids.has(t.id))
    return [...extra, ...channelTasks]
  }, [channelTasks, videoTasks, view])

  // Filtered tasks for the channel view
  const filteredChannelTasks = useMemo(() => {
    if (!search) return mergedChannelTasks
    const q = search.toLowerCase()
    return mergedChannelTasks.filter(t =>
      t.title.toLowerCase().includes(q) ||
      t.url.toLowerCase().includes(q)
    )
  }, [mergedChannelTasks, search])

  // Sorted channel tasks newest first
  const sortedChannelTasks = useMemo(() => {
    return [...filteredChannelTasks].sort((a, b) => {
      const pa = a.published_at || ''
      const pb = b.published_at || ''
      if (pa && pb) return pb.localeCompare(pa)
      if (pa && !pb) return -1
      if (!pa && pb) return 1
      return (b.created_at || '').localeCompare(a.created_at || '')
    })
  }, [filteredChannelTasks])

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
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {view.type !== 'platforms' && (
            <button
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
            <h1 className="text-xl md:text-2xl font-bold text-white">
              {view.type === 'platforms' && 'Videos'}
              {view.type === 'channels' && (PLATFORM_META[view.platform]?.label || view.platform)}
              {view.type === 'videos' && view.channel}
            </h1>
            <p className="text-sm text-gray-400">
              {view.type === 'platforms' && `${totalVideos} video note${totalVideos !== 1 ? 's' : ''}`}
              {view.type === 'channels' && `${platformChannels.length} channel${platformChannels.length !== 1 ? 's' : ''}`}
              {view.type === 'videos' && (channelTasksLoading ? 'Loading...' : `${sortedChannelTasks.length} videos`)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCheckUpdates}
            disabled={checking}
            className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
            title={
              view.type === 'videos' ? `Check ${view.channel} for new videos`
                : view.type === 'channels' ? `Check ${PLATFORM_META[view.platform]?.label || view.platform} channels for new videos`
                : 'Check all channels for new videos'
            }
          >
            <RefreshCw size={16} className={checking ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">{checking ? 'Checking...' : 'Check Updates'}</span>
          </button>
          <button onClick={() => setFormOpen(!formOpen)}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors">
            <Plus size={16} /> New Video Note
          </button>
        </div>
      </div>

      {/* New note form */}
      {formOpen && (
        <div className="bg-dark-surface rounded-xl border border-dark-border overflow-hidden">
          <div className="flex items-center justify-between px-4 pt-3 pb-0">
            <h3 className="text-sm font-semibold text-white">Generate Video Notes</h3>
            <button onClick={() => setFormOpen(false)} className="p-1 text-gray-500 hover:text-white transition-colors">
              <ChevronUp size={16} />
            </button>
          </div>
          <div className="px-4 pb-4 pt-2 max-h-[50vh] overflow-y-auto custom-scrollbar">
            <VideoNoteForm onTaskCreated={handleTaskCreated} hideTitle />
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-gray-500" />
        <input type="text" value={search} onChange={e => setSearch(e.target.value)}
          placeholder={view.type === 'videos' ? 'Search videos...' : 'Search channels...'}
          className="w-full pl-9 pr-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500" />
      </div>

      {/* Horizontal platform quick-select (always visible) */}
      {sortedPlatforms.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setView({ type: 'platforms' })}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
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
            const isActive = (view.type === 'channels' || view.type === 'videos') && view.platform === p
            return (
              <button
                key={p}
                onClick={() => setView({ type: 'channels', platform: p })}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
                }`}
              >
                <PlatformIcon platform={p} size={15} className={isActive ? 'text-white' : PLATFORM_COLORS[p] || 'text-gray-400'} />
                {meta.label}
                <span className="text-xs opacity-70">({stats.total})</span>
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
                className="p-5 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors text-left"
              >
                <div className="flex items-center gap-3 mb-3">
                  <PlatformIcon platform={p} size={28} className={PLATFORM_COLORS[p] || 'text-gray-400'} />
                  <h3 className="text-lg font-semibold text-white">{meta.label}</h3>
                </div>
                <div className="flex items-center gap-4 text-sm text-gray-400">
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
          onSelectChannel={(ch) => setView({ type: 'videos', platform: view.platform, channel: ch })}
          onDeleteChannel={handleDeleteChannel}
          onCheckUpdates={handleCheckChannelUpdates}
        />
      ) : (
        /* Video list for selected channel */
        channelTasksLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
          </div>
        ) : (
          <VideoList
            videos={sortedChannelTasks}
            onDelete={handleDelete}
            onRetry={handleRetry}
            onCancel={handleCancel}
          />
        )
      )}
    </div>
  )
}


function ChannelList({ channels, onSelectChannel, onDeleteChannel, onCheckUpdates }: {
  channels: VideoChannelStat[]
  onSelectChannel: (ch: string) => void
  onDeleteChannel?: (ch: string) => Promise<void> | void
  onCheckUpdates?: (ch: string) => Promise<void>
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
      {channels.map(ch => {
        const imgSrc = ch.channel_avatar || ch.thumbnail
        return (
          <div
            key={ch.channel}
            className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
          >
            <div className="flex flex-col sm:flex-row sm:items-start gap-4">
              <div className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0 cursor-pointer" onClick={() => onSelectChannel(ch.channel)}>
                {imgSrc ? (
                  <img
                    src={imgSrc}
                    alt=""
                    className={`w-14 h-14 md:w-20 md:h-20 flex-shrink-0 bg-dark-hover object-cover ${ch.channel_avatar ? 'rounded-full' : 'rounded-lg'}`}
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                    referrerPolicy="no-referrer"
                  />
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
              </div>

              <div className="flex items-center gap-2 justify-end sm:justify-start">
                <button
                  onClick={() => onSelectChannel(ch.channel)}
                  className="flex items-center gap-1 px-3 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors text-sm"
                >
                  <ExternalLink size={16} />
                  <span className="hidden sm:inline">Videos</span>
                </button>
                {ch.channel_url && (
                  <a
                    href={ch.channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
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
                    disabled={refreshing === ch.channel}
                    className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                    title="Check for new videos"
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
                        disabled={deleting}
                        className="px-2 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors text-xs disabled:opacity-50"
                      >
                        {deleting ? 'Deleting...' : 'Confirm'}
                      </button>
                      <button
                        onClick={() => setConfirmDelete(null)}
                        className="px-2 py-1.5 bg-dark-hover hover:bg-dark-border text-gray-400 rounded-lg transition-colors text-xs"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmDelete(ch.channel)}
                      className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors disabled:opacity-50"
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

function getErrorHint(task: VideoTask): string | null {
  const err = (task.error || '').toLowerCase()
  const msg = (task.message || '').toLowerCase()
  const combined = err + ' ' + msg
  if (combined.includes('login') || combined.includes('cookie') || combined.includes('403') || combined.includes('sign in') || combined.includes('412'))
    return 'This video may require login. Go to Settings → Platform Accounts and upload cookies or scan QR code for this platform.'
  if (combined.includes('not found') || combined.includes('404') || combined.includes('unavailable') || combined.includes('removed'))
    return 'The video could not be found or is no longer available. Check the URL and try again.'
  if (combined.includes('geo') || combined.includes('region') || combined.includes('country'))
    return 'This video may be region-restricted. Try using a VPN or a different region.'
  if (combined.includes('private'))
    return 'This video is private. Make sure you have access and upload platform cookies in Settings.'
  if (combined.includes('age') || combined.includes('restricted'))
    return 'This video is age-restricted. Upload platform cookies in Settings to verify your account.'
  if (combined.includes('timeout') || combined.includes('timed out'))
    return 'The request timed out. Try again later or check your connection.'
  if (combined.includes('copyright') || combined.includes('blocked'))
    return 'This video is blocked due to copyright. It cannot be processed.'
  if (combined.includes('rate limit') || combined.includes('429'))
    return 'Too many requests. Wait a few minutes and try again.'
  if (combined.includes('unsupported'))
    return 'This URL format is not supported. Check the URL and try again.'
  return 'Something went wrong. Try again, or check Settings → Platform Accounts if the video requires login.'
}

function VideoList({ videos, onDelete, onRetry, onCancel }: {
  videos: VideoTask[]
  onDelete: (id: string) => void
  onRetry: (id: string) => void
  onCancel: (id: string) => void
}) {
  const navigate = useNavigate()
  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    return `${m} min`
  }

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: 'Pending', parsing: 'Parsing', downloading: 'Downloading',
      transcribing: 'Transcribing', summarizing: 'Summarizing', saving: 'Saving',
      success: 'Done', failed: 'Failed', cancelled: 'Cancelled',
      discovered: 'Discovered',
    }
    return labels[status] || status
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
    <div className="space-y-3">
      {videos.map(task => {
        const isFailed = task.status === 'failed'
        const errorMsg = task.error || task.message || ''
        const hint = isFailed ? getErrorHint(task) : null
        const displayTitle = getDisplayTitle(task)

        const isClickable = task.status === 'success'
        return (
        <div
          key={task.id}
          onClick={isClickable ? () => navigate(`/videos/${task.id}`) : undefined}
          className={`p-3 md:p-4 bg-dark-surface border rounded-xl transition-colors ${
            isFailed ? 'border-red-500/30 hover:border-red-500/50' : 'border-dark-border hover:border-dark-hover'
          } ${isClickable ? 'cursor-pointer' : ''}`}
        >
          <div className="flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
            {task.thumbnail ? (
              <img
                src={task.thumbnail}
                alt=""
                className="w-full sm:w-40 md:w-48 h-24 sm:h-24 md:h-28 rounded-lg object-cover flex-shrink-0 bg-dark-hover"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className={`hidden sm:flex w-40 md:w-48 h-24 md:h-28 rounded-lg items-center justify-center flex-shrink-0 ${
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
                {task.published_at && (
                  <span>{task.published_at.slice(0, 10)}</span>
                )}
                {task.created_at && task.created_at.slice(0, 10) !== (task.published_at || '').slice(0, 10) && (
                  <span className="text-gray-500">imported {task.created_at.slice(0, 10)}</span>
                )}
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
                    className="flex items-center gap-1 text-red-500 hover:text-red-400 transition-colors"
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
                {task.status === 'pending' && (
                  <span className="flex items-center gap-1 text-gray-500">
                    <Clock size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Pending</span>
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
                  <p className={`text-xs text-red-400/80 ${expandedErrors.has(task.id) ? '' : 'line-clamp-1'}`}>
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

            <div className="flex items-center gap-2 justify-end sm:justify-start" onClick={e => e.stopPropagation()}>
              {(() => {
                if (task.status === 'success') {
                  return (
                    <>
                      <button
                        onClick={() => onRetry(task.id)}
                        className="flex items-center gap-2 px-3 py-2 bg-dark-hover hover:bg-dark-border text-gray-300 rounded-lg transition-colors"
                        title="Re-process video"
                      >
                        <RefreshCw size={16} />
                        <span className="hidden sm:inline">Re-Process</span>
                      </button>
                      <Link
                        to={`/videos/${task.id}`}
                        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
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
                      onClick={() => onRetry(task.id)}
                      className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
                      title="Start processing this video"
                    >
                      <Play size={16} />
                      Process
                    </button>
                  )
                }

                if (isProcessing(task.status)) {
                  return (
                    <div className="flex items-center gap-3 px-4 py-2 bg-dark-hover rounded-lg min-w-[140px]">
                      <Loader2 size={16} className="animate-spin text-indigo-400" />
                      <div className="flex-1">
                        <div className="text-xs text-gray-400 mb-1">
                          {task.progress > 0
                            ? `${getStatusLabel(task.status)} ${Math.round(task.progress)}%`
                            : getStatusLabel(task.status)}
                        </div>
                        <div className="h-1.5 bg-dark-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 transition-all duration-300"
                            style={{ width: `${Math.min(task.progress, 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )
                }

                return (
                  <button
                    onClick={() => onRetry(task.id)}
                    className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
                  >
                    <RotateCcw size={16} />
                    Retry
                  </button>
                )
              })()}

              {task.url && !isProcessing(task.status) && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
                  title="Open original video"
                >
                  <ExternalLink size={16} />
                </a>
              )}

              {!isProcessing(task.status) && (
                <button
                  onClick={() => onDelete(task.id)}
                  className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors"
                  title="Delete video"
                >
                  <Trash2 size={16} />
                </button>
              )}

              {isProcessing(task.status) && (
                <button
                  onClick={() => onCancel(task.id)}
                  className="p-2 bg-dark-hover hover:bg-orange-600/20 text-orange-400 rounded-lg transition-colors"
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
