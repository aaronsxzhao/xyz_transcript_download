import { useEffect, useState, useCallback } from 'react'
import { Trash2, RefreshCw, Search, CheckCircle, XCircle, Loader2, Clock, RotateCcw, Square } from 'lucide-react'
import { fetchVideoTasks, deleteVideoTask, retryVideoTask, cancelVideoTask, type VideoTask } from '../../lib/api'
import { useStore } from '../../lib/store'

interface Props {
  onSelect?: (task: VideoTask) => void
}

export default function VideoHistory({ onSelect }: Props) {
  const { videoTasks, setVideoTasks, selectedVideoTaskId, setSelectedVideoTaskId } = useStore()
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchVideoTasks()
      setVideoTasks(data.tasks)
    } catch (e: any) {
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

  const handleDelete = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteVideoTask(taskId)
      useStore.getState().removeVideoTask(taskId)
      if (selectedVideoTaskId === taskId) {
        setSelectedVideoTaskId(null)
      }
    } catch (e) {
      console.error('Delete failed:', e)
    }
  }

  const handleRetry = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await retryVideoTask(taskId)
      loadTasks()
    } catch (e) {
      console.error('Retry failed:', e)
    }
  }

  const handleCancel = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await cancelVideoTask(taskId)
      loadTasks()
    } catch (e) {
      console.error('Cancel failed:', e)
    }
  }

  const handleSelect = (task: VideoTask) => {
    setSelectedVideoTaskId(task.id)
    onSelect?.(task)
  }

  const filtered = search
    ? videoTasks.filter(t =>
        t.title.toLowerCase().includes(search.toLowerCase()) ||
        t.url.toLowerCase().includes(search.toLowerCase())
      )
    : videoTasks

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle size={14} className="text-green-500" />
      case 'failed': return <XCircle size={14} className="text-red-500" />
      case 'cancelled': return <Square size={14} className="text-orange-400" />
      case 'pending': return <Clock size={14} className="text-gray-500" />
      default: return <Loader2 size={14} className="text-indigo-400 animate-spin" />
    }
  }

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: 'Pending',
      parsing: 'Parsing',
      downloading: 'Downloading',
      transcribing: 'Transcribing',
      summarizing: 'Summarizing',
      saving: 'Saving',
      success: 'Done',
      failed: 'Failed',
      cancelled: 'Cancelled',
    }
    return labels[status] || status
  }

  const getPlatformIcon = (platform: string) => {
    const icons: Record<string, string> = {
      bilibili: '📺',
      youtube: '▶️',
      douyin: '🎵',
      kuaishou: '⚡',
      local: '📁',
    }
    return icons[platform] || '🎬'
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">History</h3>
        <button
          onClick={loadTasks}
          disabled={loading}
          className="p-1 text-gray-500 hover:text-white transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-3">
        <Search size={14} className="absolute left-2.5 top-2.5 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search..."
          className="w-full pl-8 pr-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto space-y-1.5 custom-scrollbar">
        {filtered.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-8">No tasks yet</p>
        ) : (
          filtered.map(task => (
            <div
              key={task.id}
              onClick={() => handleSelect(task)}
              className={`p-2.5 rounded-lg cursor-pointer transition-colors group ${
                selectedVideoTaskId === task.id
                  ? 'bg-indigo-600/20 border border-indigo-500/40'
                  : 'bg-dark-hover hover:bg-dark-border border border-transparent'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className="text-lg mt-0.5 flex-shrink-0">
                  {task.thumbnail ? (
                    <img
                      src={task.thumbnail}
                      alt=""
                      className="w-10 h-7 rounded object-cover"
                      onError={e => {
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    getPlatformIcon(task.platform)
                  )}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">
                    {task.title || 'Untitled'}
                  </p>
                  <div className="flex items-center gap-1.5 mt-1">
                    {getStatusIcon(task.status)}
                    <span className="text-xs text-gray-500">
                      {task.status === 'failed' && task.error
                        ? ({
                            BILIBILI_LOGIN_REQUIRED: 'Login required',
                            LOGIN_REQUIRED: 'Login required',
                            COOKIES_REQUIRED: 'Cookies needed',
                            AGE_RESTRICTED: 'Age restricted',
                            VIDEO_PRIVATE: 'Private video',
                            VIDEO_UNAVAILABLE: 'Unavailable',
                            GEO_RESTRICTED: 'Region blocked',
                            COPYRIGHT_BLOCKED: 'Copyright blocked',
                            RATE_LIMITED: 'Rate limited',
                            FFMPEG_MISSING: 'FFmpeg missing',
                            UNSUPPORTED_URL: 'Bad URL',
                          }[task.error] || getStatusLabel(task.status))
                        : getStatusLabel(task.status)}
                    </span>
                    {task.status !== 'success' && task.status !== 'failed' && task.progress > 0 && (
                      <span className="text-xs text-gray-500">
                        {Math.round(task.progress)}%
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                  {!['success', 'failed', 'cancelled', 'pending'].includes(task.status) && (
                    <button
                      onClick={e => handleCancel(task.id, e)}
                      className="p-1 text-gray-600 hover:text-orange-400 transition-colors"
                      title="Cancel"
                    >
                      <Square size={13} className="fill-current" />
                    </button>
                  )}
                  {(task.status === 'failed' || task.status === 'cancelled') && (
                    <button
                      onClick={e => handleRetry(task.id, e)}
                      className="p-1 text-gray-600 hover:text-indigo-400 transition-colors"
                      title="Retry"
                    >
                      <RotateCcw size={13} />
                    </button>
                  )}
                  <button
                    onClick={e => handleDelete(task.id, e)}
                    className="p-1 text-gray-600 hover:text-red-400 transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              {/* Progress bar for active tasks */}
              {!['success', 'failed', 'pending'].includes(task.status) && (
                <div className="mt-2 h-1 bg-dark-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 transition-all duration-300"
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
