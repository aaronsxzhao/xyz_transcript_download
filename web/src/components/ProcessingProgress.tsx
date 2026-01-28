import type { ProcessingJob } from '../lib/api'
import { getStatusIcon, getStatusColor, isActiveStatus } from '../lib/statusUtils'

interface ProcessingProgressProps {
  job: ProcessingJob
}

export default function ProcessingProgress({ job }: ProcessingProgressProps) {
  const isActive = isActiveStatus(job.status)
  
  return (
    <div className="p-4 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {getStatusIcon(job.status, 'md')}
          <div>
            <p className="font-medium text-white">
              {job.episode_title || `Job ${job.job_id}`}
            </p>
            <p className="text-sm text-gray-400">{job.message}</p>
          </div>
        </div>
        <span className="text-xs text-gray-500 uppercase">{job.status}</span>
      </div>
      
      {/* Progress bar */}
      {isActive && (
        <div className="h-2 bg-dark-hover rounded-full overflow-hidden">
          <div 
            className={`h-full ${getStatusColor(job.status)} transition-all duration-300`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
      )}
    </div>
  )
}
