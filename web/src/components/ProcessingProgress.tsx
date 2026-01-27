import { Loader2, CheckCircle, XCircle, Clock } from 'lucide-react'
import type { ProcessingJob } from '../lib/api'

interface ProcessingProgressProps {
  job: ProcessingJob
}

export default function ProcessingProgress({ job }: ProcessingProgressProps) {
  const getStatusIcon = () => {
    switch (job.status) {
      case 'completed':
        return <CheckCircle className="text-green-500" size={20} />
      case 'failed':
        return <XCircle className="text-red-500" size={20} />
      case 'pending':
        return <Clock className="text-gray-500" size={20} />
      default:
        return <Loader2 className="text-indigo-500 animate-spin" size={20} />
    }
  }
  
  const getStatusColor = () => {
    switch (job.status) {
      case 'completed':
        return 'bg-green-500'
      case 'failed':
        return 'bg-red-500'
      case 'pending':
        return 'bg-gray-500'
      default:
        return 'bg-indigo-500'
    }
  }
  
  return (
    <div className="p-4 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {getStatusIcon()}
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
      {job.status !== 'pending' && job.status !== 'completed' && job.status !== 'failed' && (
        <div className="h-2 bg-dark-hover rounded-full overflow-hidden">
          <div 
            className={`h-full ${getStatusColor()} transition-all duration-300`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
      )}
    </div>
  )
}
