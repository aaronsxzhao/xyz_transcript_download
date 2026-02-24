/**
 * Unified processing panel showing active podcast AND video jobs with progress
 */
import { useState, useEffect, useRef } from 'react'
import { ChevronUp, ChevronDown, Activity, X, Trash2, RotateCcw, Radio, Video } from 'lucide-react'
import { useStore } from '../lib/store'
import { cancelJob, deleteJob, retryJob, type ProcessingJob } from '../lib/api'
import { getStatusColor, getStatusText, isActiveStatus } from '../lib/statusUtils'

const MOBILE_BREAKPOINT = 640

export default function ProcessingPanel() {
  const { jobs, videoTasks, wsConnected, removeJob } = useStore()
  const [expanded, setExpanded] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= MOBILE_BREAKPOINT : true
  )
  const prevActiveCountRef = useRef(0)

  // Podcast jobs
  const activeJobs = jobs.filter(job =>
    job.status !== 'completed' && job.status !== 'failed' && job.status !== 'cancelled'
  )
  const completedJobs = jobs.filter(job =>
    job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
  )

  // Active video tasks
  const activeVideoTasks = videoTasks.filter(t =>
    !['success', 'failed', 'cancelled'].includes(t.status)
  )

  const totalActive = activeJobs.length + activeVideoTasks.length
  const totalItems = jobs.length + activeVideoTasks.length

  useEffect(() => {
    if (totalActive > prevActiveCountRef.current && window.innerWidth < MOBILE_BREAKPOINT) {
      setExpanded(true)
    }
    prevActiveCountRef.current = totalActive
  }, [totalActive])

  useEffect(() => {
    if (totalActive === 0 && window.innerWidth < MOBILE_BREAKPOINT) {
      const timer = setTimeout(() => setExpanded(false), 2000)
      return () => clearTimeout(timer)
    }
  }, [totalActive])

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < MOBILE_BREAKPOINT && totalActive === 0) {
        setExpanded(false)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [totalActive])

  const handleDismiss = async (jobId: string) => {
    try { await deleteJob(jobId) } catch { /* ignore */ }
    removeJob(jobId)
  }

  const handleClearCompleted = async () => {
    for (const job of completedJobs) {
      try { await deleteJob(job.job_id) } catch { /* ignore */ }
      removeJob(job.job_id)
    }
  }

  if (totalItems === 0) return null

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:right-auto z-40 sm:w-96 bg-dark-surface border border-dark-border rounded-xl shadow-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-2 sm:p-3 bg-dark-hover">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 min-h-[44px] sm:min-h-0"
        >
          <Activity className="w-5 h-5 sm:w-4 sm:h-4 text-indigo-400" />
          <span className="font-medium text-sm">
            Processing
            {totalActive > 0 ? ` (${totalActive} active)` : ''}
          </span>
        </button>
        <div className="flex items-center gap-1 sm:gap-2">
          {!wsConnected && (
            <span className="text-xs text-yellow-500">Offline</span>
          )}
          {completedJobs.length > 0 && (
            <button
              onClick={handleClearCompleted}
              className="p-2 sm:p-1 min-w-[44px] min-h-[44px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-white hover:bg-dark-border rounded transition-colors"
              title="Clear completed"
            >
              <Trash2 size={16} className="sm:w-3.5 sm:h-3.5" />
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-2 sm:p-1 min-w-[44px] min-h-[44px] sm:min-w-0 sm:min-h-0 flex items-center justify-center"
          >
            {expanded ? <ChevronDown size={20} className="sm:w-4 sm:h-4" /> : <ChevronUp size={20} className="sm:w-4 sm:h-4" />}
          </button>
        </div>
      </div>

      {/* Jobs list */}
      {expanded && (
        <div className="max-h-48 sm:max-h-72 overflow-y-auto divide-y divide-dark-border">
          {/* Active video tasks */}
          {activeVideoTasks.map(task => (
            <VideoJobItem key={`v-${task.id}`} task={task} />
          ))}
          {/* Active podcast jobs */}
          {activeJobs.map(job => (
            <PodcastJobItem key={job.job_id} job={job} showCancel />
          ))}
          {/* Completed podcast jobs */}
          {completedJobs.slice(0, 3).map(job => (
            <PodcastJobItem key={job.job_id} job={job} onDismiss={() => handleDismiss(job.job_id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function VideoJobItem({ task }: { task: { id: string; title: string; status: string; progress: number; message: string; platform: string } }) {
  const statusColor = task.status === 'downloading' ? 'bg-blue-500'
    : task.status === 'transcribing' ? 'bg-purple-500'
    : task.status === 'summarizing' ? 'bg-indigo-500'
    : 'bg-gray-500'

  return (
    <div className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        <Video size={16} className="text-cyan-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {task.title || 'Processing video...'}
          </p>
          <p className="text-xs text-gray-500">
            {task.message || task.status}
          </p>
        </div>
      </div>
      <div className="relative h-1.5 bg-dark-border rounded-full overflow-hidden">
        <div
          className={`absolute left-0 top-0 h-full ${statusColor} transition-all duration-300`}
          style={{ width: `${Math.min(task.progress, 100)}%` }}
        />
        {task.progress === 0 && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
        )}
      </div>
      <div className="flex justify-between items-center">
        <p className="text-xs text-cyan-400">{task.message || 'Processing...'}</p>
        <p className="text-xs font-medium text-white">{Math.round(task.progress)}%</p>
      </div>
    </div>
  )
}

function PodcastJobItem({ job, showCancel = false, onDismiss }: { job: ProcessingJob; showCancel?: boolean; onDismiss?: () => void }) {
  const [cancelling, setCancelling] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const { removeJob } = useStore()

  const handleCancel = async () => {
    setCancelling(true)
    try { await cancelJob(job.job_id) } catch (err) { console.error('Cancel failed:', err) }
    finally { setCancelling(false) }
  }

  const handleRetry = async () => {
    setRetrying(true)
    try { await retryJob(job.job_id) } catch (err) { console.error('Retry failed:', err); removeJob(job.job_id) }
    finally { setRetrying(false) }
  }

  const isActive = isActiveStatus(job.status)
  const canRetry = job.status === 'failed' || job.status === 'cancelled'

  return (
    <div className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        <Radio size={16} className="text-indigo-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {job.episode_title || 'Processing episode...'}
          </p>
          <p className="text-xs text-gray-500">
            {job.message || getStatusText(job.status)}
          </p>
        </div>
        {showCancel && isActive && job.status !== 'cancelling' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="p-2 sm:p-1 min-w-[40px] min-h-[40px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors -mr-1"
            title="Cancel"
          >
            <X className="w-5 h-5 sm:w-4 sm:h-4" />
          </button>
        )}
        {canRetry && job.episode_id && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="p-2 sm:p-1 min-w-[40px] min-h-[40px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-green-400 hover:bg-green-400/10 rounded transition-colors"
            title="Retry"
          >
            <RotateCcw className={`w-5 h-5 sm:w-4 sm:h-4 ${retrying ? 'animate-spin' : ''}`} />
          </button>
        )}
        {onDismiss && !isActive && (
          <button
            onClick={onDismiss}
            className="p-2 sm:p-1 min-w-[40px] min-h-[40px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-white hover:bg-dark-border rounded transition-colors -mr-1"
            title="Dismiss"
          >
            <X className="w-5 h-5 sm:w-4 sm:h-4" />
          </button>
        )}
      </div>

      {isActive && (
        <div className="relative h-1.5 bg-dark-border rounded-full overflow-hidden">
          <div
            className={`absolute left-0 top-0 h-full ${getStatusColor(job.status)} transition-all duration-300`}
            style={{ width: `${Math.min(job.progress, 100)}%` }}
          />
          {job.progress === 0 && (
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
          )}
        </div>
      )}

      {isActive && (
        <div className="flex justify-between items-center">
          <p className="text-xs text-indigo-400">{job.message || 'Processing...'}</p>
          <p className="text-xs font-medium text-white">{Math.round(job.progress)}%</p>
        </div>
      )}
    </div>
  )
}
