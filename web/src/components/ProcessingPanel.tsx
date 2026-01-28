/**
 * Processing panel that shows active jobs with progress
 */
import { useState } from 'react'
import { ChevronUp, ChevronDown, Radio, X } from 'lucide-react'
import { useStore } from '../lib/store'
import { cancelJob, type ProcessingJob } from '../lib/api'
import { getStatusIcon, getStatusColor, getStatusText, isActiveStatus } from '../lib/statusUtils'

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
    <div className="fixed bottom-4 left-4 right-4 sm:right-auto z-40 sm:w-80 bg-dark-surface border border-dark-border rounded-xl shadow-xl overflow-hidden">
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
  
  const isActive = isActiveStatus(job.status)
  
  return (
    <div className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        {getStatusIcon(job.status)}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {job.episode_title || 'Processing episode...'}
          </p>
          <p className="text-xs text-gray-500">
            {job.message || getStatusText(job.status)}
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
            className={`absolute left-0 top-0 h-full ${getStatusColor(job.status)} transition-all duration-300`}
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
