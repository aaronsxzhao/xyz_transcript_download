/**
 * Processing panel that shows active jobs with progress
 */
import { useState, useEffect, useRef } from 'react'
import { ChevronUp, ChevronDown, Radio, X, Trash2 } from 'lucide-react'
import { useStore } from '../lib/store'
import { cancelJob, type ProcessingJob } from '../lib/api'
import { getStatusIcon, getStatusColor, getStatusText, isActiveStatus } from '../lib/statusUtils'

// Mobile breakpoint (matches Tailwind's sm)
const MOBILE_BREAKPOINT = 640

export default function ProcessingPanel() {
  const { jobs, wsConnected, removeJob, clearCompletedJobs } = useStore()
  // Start collapsed on mobile, expanded on desktop
  const [expanded, setExpanded] = useState(() => 
    typeof window !== 'undefined' ? window.innerWidth >= MOBILE_BREAKPOINT : true
  )
  const prevActiveCountRef = useRef(0)
  
  // Only show if there are active jobs
  const activeJobs = jobs.filter(job => 
    job.status !== 'completed' && job.status !== 'failed' && job.status !== 'cancelled'
  )
  const completedJobs = jobs.filter(job => 
    job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
  )
  
  // Auto-expand when new jobs start on mobile
  useEffect(() => {
    if (activeJobs.length > prevActiveCountRef.current && window.innerWidth < MOBILE_BREAKPOINT) {
      setExpanded(true)
    }
    prevActiveCountRef.current = activeJobs.length
  }, [activeJobs.length])
  
  // Auto-collapse on mobile when no active jobs (with delay to show completion)
  useEffect(() => {
    if (activeJobs.length === 0 && window.innerWidth < MOBILE_BREAKPOINT) {
      const timer = setTimeout(() => {
        setExpanded(false)
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [activeJobs.length])
  
  // Auto-collapse when window resizes to mobile
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < MOBILE_BREAKPOINT && activeJobs.length === 0) {
        setExpanded(false)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [activeJobs.length])
  
  if (jobs.length === 0) {
    return null
  }
  
  return (
    <div className="fixed bottom-4 left-4 right-4 sm:right-auto z-40 sm:w-80 bg-dark-surface border border-dark-border rounded-xl shadow-xl overflow-hidden">
      {/* Header - larger touch targets on mobile */}
      <div className="flex items-center justify-between p-2 sm:p-3 bg-dark-hover">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 min-h-[44px] sm:min-h-0"
        >
          <Radio className="w-5 h-5 sm:w-4 sm:h-4 text-indigo-400" />
          <span className="font-medium text-sm">
            Processing {activeJobs.length > 0 ? `(${activeJobs.length} active)` : ''}
          </span>
        </button>
        <div className="flex items-center gap-1 sm:gap-2">
          {!wsConnected && (
            <span className="text-xs text-yellow-500">Offline</span>
          )}
          {completedJobs.length > 0 && (
            <button
              onClick={clearCompletedJobs}
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
      
      {/* Jobs list - smaller max-height on mobile */}
      {expanded && (
        <div className="max-h-48 sm:max-h-64 overflow-y-auto divide-y divide-dark-border">
          {activeJobs.map((job) => (
            <JobItem key={job.job_id} job={job} showCancel />
          ))}
          {completedJobs.slice(0, 3).map((job) => (
            <JobItem key={job.job_id} job={job} onDismiss={() => removeJob(job.job_id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function JobItem({ job, showCancel = false, onDismiss }: { job: ProcessingJob; showCancel?: boolean; onDismiss?: () => void }) {
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
        {/* Cancel button for active jobs - larger touch target on mobile */}
        {showCancel && isActive && job.status !== 'cancelling' && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="p-2 sm:p-1 min-w-[40px] min-h-[40px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors -mr-1"
            title="Cancel processing"
          >
            <X className="w-5 h-5 sm:w-4 sm:h-4" />
          </button>
        )}
        {/* Dismiss button for completed jobs - larger touch target on mobile */}
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
      
      {/* Progress percentage - always show for active jobs */}
      {isActive && (
        <div className="flex justify-between items-center">
          <p className="text-xs text-indigo-400">
            {job.message || 'Processing...'}
          </p>
          <p className="text-xs font-medium text-white">
            {Math.round(job.progress)}%
          </p>
        </div>
      )}
    </div>
  )
}
