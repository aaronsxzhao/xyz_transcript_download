import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Video, Radio, ExternalLink, X } from 'lucide-react'
import type { ProcessingJob } from '../lib/api'
import { getStatusIcon, getStatusColor, isActiveStatus } from '../lib/statusUtils'

interface ProcessingProgressProps {
  job: ProcessingJob
  link?: string
  kind?: 'podcast' | 'video'
  onCancel?: (id: string) => Promise<void>
}

export default function ProcessingProgress({ job, link, kind, onCancel }: ProcessingProgressProps) {
  const isActive = isActiveStatus(job.status)
  const isDone = job.status === 'completed' || job.status === 'success'
  const clickable = isDone && !!link
  const [cancelling, setCancelling] = useState(false)

  const handleCancel = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!onCancel || cancelling) return
    setCancelling(true)
    try { await onCancel(job.job_id) } catch { /* ignore */ }
    finally { setCancelling(false) }
  }

  const content = (
    <div className={`p-4 bg-dark-surface border rounded-xl transition-colors ${
      clickable ? 'border-dark-border hover:border-indigo-500/50 cursor-pointer' : 'border-dark-border'
    }`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-3 min-w-0">
          {getStatusIcon(job.status === 'success' ? 'completed' : job.status, 'md')}
          <div className="min-w-0 flex-1">
            <p className="font-medium text-white truncate flex items-center gap-2">
              {kind === 'video' && <Video size={14} className="text-cyan-400 flex-shrink-0" />}
              {kind === 'podcast' && <Radio size={14} className="text-indigo-400 flex-shrink-0" />}
              {job.episode_title || `Job ${job.job_id}`}
            </p>
            <p className="text-sm text-gray-400 truncate">{job.message}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          <span className="text-xs text-gray-500 uppercase">{job.status === 'success' ? 'completed' : job.status}</span>
          {clickable && <ExternalLink size={12} className="text-indigo-400" />}
          {isActive && onCancel && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="p-1 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
              title="Cancel"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>
      
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

  if (clickable) {
    return <Link to={link}>{content}</Link>
  }
  return content
}
