/**
 * Processing panel that shows active jobs with progress
 */
import { useState } from 'react'
import { ChevronUp, ChevronDown, Loader2, CheckCircle, XCircle, Radio, X, Ban } from 'lucide-react'
import { useStore } from '../lib/store'
import { cancelJob, type ProcessingJob } from '../lib/api'

export default function ProcessingPanel() {
  const { jobs, wsConnected } = useStore()
  const [expanded, setExpanded] = useState(true)
  
  // Only show if there are active jobs
  const activeJobs = jobs.filter(job => 
    job.status !== 'completed' && job.status !== 'failed' && job.status !== 'cancelled'
  )
  const completedJobs = jobs.filter(job => 
    job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
  )
  
  if (jobs.length === 0) {
    return null
  }
  
  return (
    <div className="fixed bottom-4 left-4 z-40 w-80 bg-dark-surface border border-dark-border rounded-xl shadow-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 bg-dark-hover hover:bg-dark-border transition-colors"
      >
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-indigo-400" />
          <span className="font-medium text-sm">
            Processing {activeJobs.length > 0 ? `(${activeJobs.length} active)` : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {!wsConnected && (
            <span className="text-xs text-yellow-500">Offline</span>
          )}
          {expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </div>
      </button>
      
      {/* Jobs list */}
      {expanded && (
        <div className="max-h-64 overflow-y-auto divide-y divide-dark-border">
          {activeJobs.map((job) => (
            <JobItem key={job.job_id} job={job} showCancel />
          ))}
          {completedJobs.slice(0, 3).map((job) => (
            <JobItem key={job.job_id} job={job} />
          ))}
        </div>
      )}
    </div>
  )
}

function JobItem({ job, showCancel = false }: { job: ProcessingJob; showCancel?: boolean }) {
  const [cancelling, setCancelling] = useState(false)
  
  const handleCancel = async () => {
    setCancelling(true)
    try {
      await cancelJob(job.job_id)
    } catch (err) {
      console.error('Failed to cancel job:', err)
    } finally {
      setCancelling(false)
    }
  }
  
  const getStatusIcon = () => {
    switch (job.status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-400" />
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-400" />
      case 'cancelled':
        return <Ban className="w-4 h-4 text-gray-400" />
      case 'cancelling':
        return <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />
      default:
        return <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
    }
  }
  
  const getStatusColor = () => {
    switch (job.status) {
      case 'completed':
        return 'bg-green-500'
      case 'failed':
        return 'bg-red-500'
      case 'cancelled':
        return 'bg-gray-500'
      case 'cancelling':
        return 'bg-yellow-500'
      case 'downloading':
        return 'bg-blue-500'
      case 'transcribing':
        return 'bg-purple-500'
      case 'summarizing':
        return 'bg-indigo-500'
      default:
        return 'bg-gray-500'
    }
  }
  
  const getStatusText = () => {
    switch (job.status) {
      case 'pending':
        return 'Waiting...'
      case 'downloading':
        return 'Downloading audio...'
      case 'transcribing':
        return 'Transcribing...'
      case 'summarizing':
        return 'Summarizing...'
      case 'completed':
        return 'Done!'
      case 'failed':
        return 'Failed'
      case 'cancelled':
        return 'Cancelled'
      case 'cancelling':
        return 'Cancelling (after current step)...'
      default:
        return job.status
    }
  }
  
  const isActive = !['completed', 'failed', 'cancelled'].includes(job.status)
  
  return (
    <div className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        {getStatusIcon()}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {job.episode_title || 'Processing episode...'}
          </p>
          <p className="text-xs text-gray-500">
            {job.message || getStatusText()}
          </p>
        </div>
        {/* Cancel button */}
        {showCancel && isActive && job.status !== 'cancelling' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="p-1 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
            title="Cancel processing"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
      
      {/* Progress bar */}
      {isActive && (
        <div className="relative h-1.5 bg-dark-border rounded-full overflow-hidden">
          <div
            className={`absolute left-0 top-0 h-full ${getStatusColor()} transition-all duration-300`}
            style={{ width: `${Math.min(job.progress, 100)}%` }}
          />
          {/* Animated shimmer for indeterminate progress */}
          {job.progress === 0 && (
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
          )}
        </div>
      )}
      
      {/* Progress percentage */}
      {job.progress > 0 && isActive && (
        <p className="text-xs text-gray-500 text-right">
          {Math.round(job.progress)}%
        </p>
      )}
    </div>
  )
}
