import { useCallback, useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus, ChevronUp, Video, Search, Trash2, RefreshCw, RotateCcw, Square,
  CheckCircle, XCircle, Clock, Loader2, ArrowLeft, ExternalLink,
} from 'lucide-react'
import VideoNoteForm from '../components/video/VideoNoteForm'
import { useStore } from '../lib/store'
import {
  fetchVideoTasks, deleteVideoTask, retryVideoTask, cancelVideoTask,
  type VideoTask,
} from '../lib/api'

const PLATFORM_META: Record<string, { label: string; icon: string }> = {
  bilibili: { label: 'Bilibili', icon: '📺' },
  youtube: { label: 'YouTube', icon: '▶️' },
  douyin: { label: '抖音', icon: '🎵' },
  kuaishou: { label: '快手', icon: '⚡' },
  local: { label: 'Local', icon: '📁' },
}

type View = { type: 'platforms' } | { type: 'channels'; platform: string } | { type: 'videos'; platform: string; channel: string }

export default function Videos() {
  const { videoTasks, setVideoTasks, removeVideoTask } = useStore()
  const [formOpen, setFormOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState<View>({ type: 'platforms' })

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchVideoTasks()
      setVideoTasks(data.tasks)
    } catch (e) {
      console.error('Failed to load tasks:', e)
    } finally {
      setLoading(false)
    }
  }, [setVideoTasks])

  const hasActiveTasks = videoTasks.some(t =>
    !['success', 'failed', 'cancelled'].includes(t.status)
  )

  useEffect(() => {
    loadTasks()
    const interval = setInterval(loadTasks, hasActiveTasks ? 3000 : 15000)
    return () => clearInterval(interval)
  }, [loadTasks, hasActiveTasks])

  const handleTaskCreated = (taskId: string) => {
    useStore.getState().updateVideoTask({
      id: taskId, url: '', platform: '', title: '', thumbnail: '',
      channel: '', channel_url: '', channel_avatar: '',
      status: 'pending', progress: 0, message: 'Queued for processing...',
      markdown: '', transcript: null, style: '', model: '', formats: [],
      quality: '', extras: '', video_understanding: false, video_interval: 4,
      grid_cols: 3, grid_rows: 3, duration: 0, error: '',
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    })
    setFormOpen(false)
  }

  const handleDelete = async (taskId: string) => {
    try { await deleteVideoTask(taskId); removeVideoTask(taskId) }
    catch (e) { console.error('Delete failed:', e) }
  }
  const handleRetry = async (taskId: string) => {
    try { await retryVideoTask(taskId); loadTasks() }
    catch (e) { console.error('Retry failed:', e) }
  }
  const handleCancel = async (taskId: string) => {
    try { await cancelVideoTask(taskId); loadTasks() }
    catch (e) { console.error('Cancel failed:', e) }
  }

  // Filter by search
  const filtered = useMemo(() => {
    if (!search) return videoTasks
    const q = search.toLowerCase()
    return videoTasks.filter(t =>
      t.title.toLowerCase().includes(q) ||
      t.url.toLowerCase().includes(q) ||
      t.channel.toLowerCase().includes(q)
    )
  }, [videoTasks, search])

  // Derive platforms with counts
  const platformStats = useMemo(() => {
    const stats: Record<string, { total: number; done: number }> = {}
    for (const t of filtered) {
      const p = t.platform || 'other'
      if (!stats[p]) stats[p] = { total: 0, done: 0 }
      stats[p].total++
      if (t.status === 'success') stats[p].done++
    }
    return stats
  }, [filtered])

  const sortedPlatforms = useMemo(() => {
    const order = ['bilibili', 'youtube', 'douyin', 'kuaishou', 'local']
    return Object.keys(platformStats).sort((a, b) =>
      (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
      (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
    )
  }, [platformStats])

  // Derive channels for a platform
  const getChannels = (platform: string) => {
    const channelMap: Record<string, { count: number; done: number; tasks: VideoTask[] }> = {}
    for (const t of filtered) {
      if ((t.platform || 'other') !== platform) continue
      const ch = t.channel || 'Unknown Channel'
      if (!channelMap[ch]) channelMap[ch] = { count: 0, done: 0, tasks: [] }
      channelMap[ch].count++
      channelMap[ch].tasks.push(t)
      if (t.status === 'success') channelMap[ch].done++
    }
    return channelMap
  }

  // Get videos for a platform+channel
  const getVideos = (platform: string, channel: string) => {
    return filtered.filter(t =>
      (t.platform || 'other') === platform &&
      (t.channel || 'Unknown Channel') === channel
    )
  }

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
              {view.type === 'platforms' && `${videoTasks.length} video note${videoTasks.length !== 1 ? 's' : ''}`}
              {view.type === 'channels' && `${platformStats[view.platform]?.total || 0} videos`}
              {view.type === 'videos' && `${getVideos(view.platform, view.channel).length} videos`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadTasks} disabled={loading}
            className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-gray-400">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
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
          placeholder="Search videos, channels..."
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
            All ({filtered.length})
          </button>
          {sortedPlatforms.map(p => {
            const meta = PLATFORM_META[p] || { label: p, icon: '🎬' }
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
                <span>{meta.icon}</span>
                {meta.label}
                <span className="text-xs opacity-70">({stats.total})</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Content based on view */}
      {videoTasks.length === 0 ? (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No video notes yet</p>
          <p className="text-gray-500">Create a new video note to get started</p>
        </div>
      ) : view.type === 'platforms' ? (
        /* Platform overview — show all platforms as cards */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedPlatforms.map(p => {
            const meta = PLATFORM_META[p] || { label: p, icon: '🎬' }
            const stats = platformStats[p]
            const channels = Object.keys(getChannels(p))
            return (
              <button
                key={p}
                onClick={() => setView({ type: 'channels', platform: p })}
                className="p-5 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors text-left"
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-2xl">{meta.icon}</span>
                  <h3 className="text-lg font-semibold text-white">{meta.label}</h3>
                </div>
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span>{channels.length} channel{channels.length !== 1 ? 's' : ''}</span>
                  <span>{stats.done}/{stats.total} completed</span>
                </div>
              </button>
            )
          })}
        </div>
      ) : view.type === 'channels' ? (
        /* Channel list for selected platform */
        <ChannelList
          channels={getChannels(view.platform)}
          onSelectChannel={(ch) => setView({ type: 'videos', platform: view.platform, channel: ch })}
        />
      ) : (
        /* Video list for selected channel */
        <VideoList
          videos={getVideos(view.platform, view.channel)}
          onDelete={handleDelete}
          onRetry={handleRetry}
          onCancel={handleCancel}
        />
      )}
    </div>
  )
}


function ChannelList({ channels, onSelectChannel }: {
  channels: Record<string, { count: number; done: number; tasks: VideoTask[] }>
  onSelectChannel: (ch: string) => void
}) {
  const channelNames = Object.keys(channels).sort((a, b) => {
    if (a === 'Unknown Channel') return 1
    if (b === 'Unknown Channel') return -1
    return channels[b].count - channels[a].count
  })

  if (channelNames.length === 0) {
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
      {channelNames.map(ch => {
        const info = channels[ch]
        const latestTask = info.tasks.reduce((a, b) =>
          new Date(b.updated_at) > new Date(a.updated_at) ? b : a
        , info.tasks[0])
        const latestTitle = info.tasks
          .filter(t => t.status === 'success')
          .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0]?.title

        return (
          <div
            key={ch}
            className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
          >
            <div className="flex flex-col sm:flex-row sm:items-start gap-4">
              <div className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0 cursor-pointer" onClick={() => onSelectChannel(ch)}>
                {(() => {
                  const avatar = info.tasks.find(t => t.channel_avatar)?.channel_avatar
                  const thumb = latestTask?.thumbnail
                  const imgSrc = avatar || thumb
                  if (imgSrc) {
                    return (
                      <img
                        src={imgSrc}
                        alt=""
                        className={`w-14 h-14 md:w-20 md:h-20 flex-shrink-0 bg-dark-hover object-cover ${avatar ? 'rounded-full' : 'rounded-lg'}`}
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                        referrerPolicy="no-referrer"
                      />
                    )
                  }
                  return (
                    <div className="w-14 h-14 md:w-20 md:h-20 rounded-full bg-dark-hover flex items-center justify-center flex-shrink-0">
                      <Video className="w-6 h-6 md:w-8 md:h-8 text-gray-600" />
                    </div>
                  )
                })()}

                <div className="flex-1 min-w-0">
                  <h3 className="text-base md:text-lg font-semibold text-white mb-1 line-clamp-2">
                    {ch}
                  </h3>
                  {latestTitle && (
                    <p className="text-sm text-gray-500 line-clamp-1 hidden sm:block">
                      Latest: {latestTitle}
                    </p>
                  )}
                  <p className="text-sm text-indigo-400 mt-1 md:mt-2">
                    {info.done > 0
                      ? `${info.done} / ${info.count} completed`
                      : `${info.count} video${info.count !== 1 ? 's' : ''}`
                    }
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 justify-end sm:justify-start">
                <button
                  onClick={() => onSelectChannel(ch)}
                  className="flex items-center gap-1 px-3 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors text-sm"
                >
                  <Video size={16} />
                  <span className="hidden sm:inline">Videos</span>
                </button>
                {latestTask?.channel_url && (
                  <a
                    href={latestTask.channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
                    title="Open channel page"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}


function VideoList({ videos, onDelete, onRetry, onCancel }: {
  videos: VideoTask[]
  onDelete: (id: string) => void
  onRetry: (id: string) => void
  onCancel: (id: string) => void
}) {
  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    return `${m} min`
  }

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: 'Pending', parsing: 'Parsing', downloading: 'Downloading',
      transcribing: 'Transcribing', summarizing: 'Summarizing', saving: 'Saving',
      success: 'Done', failed: 'Failed', cancelled: 'Cancelled',
    }
    return labels[status] || status
  }

  const isProcessing = (status: string) =>
    !['success', 'failed', 'pending', 'cancelled'].includes(status)

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
      {videos.map(task => (
        <div
          key={task.id}
          className="p-3 md:p-4 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
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
              <div className="hidden sm:flex w-40 md:w-48 h-24 md:h-28 rounded-lg bg-dark-hover items-center justify-center flex-shrink-0">
                <Video className="w-8 h-8 text-gray-600" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-white mb-1 line-clamp-2 text-sm md:text-base">
                {task.title || 'Untitled'}
              </h3>
              <div className="flex flex-wrap items-center gap-2 md:gap-4 text-xs md:text-sm text-gray-400">
                {task.created_at && (
                  <span>{task.created_at.slice(0, 10)}</span>
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
                  <span className="flex items-center gap-1 text-red-500">
                    <XCircle size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Failed</span>
                  </span>
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
              </div>
            </div>

            <div className="flex items-center gap-2 justify-end sm:justify-start">
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
      ))}
    </div>
  )
}
