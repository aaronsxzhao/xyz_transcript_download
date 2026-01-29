/**
 * Shared status utilities for processing jobs
 */
import { Loader2, CheckCircle, XCircle, Clock, Ban, Zap, RefreshCw } from 'lucide-react'

export type JobStatus = 
  | 'pending' 
  | 'fetching'
  | 'downloading' 
  | 'compressing'
  | 'transcribing' 
  | 'transcribing_fast'
  | 'summarizing' 
  | 'quick_ready'
  | 'refining'
  | 'merging'
  | 'completed' 
  | 'failed' 
  | 'cancelled' 
  | 'cancelling'

/**
 * Get the appropriate icon for a job status
 */
export function getStatusIcon(status: string, size: 'sm' | 'md' = 'sm') {
  const sizeClass = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5'
  
  switch (status) {
    case 'completed':
      return <CheckCircle className={`${sizeClass} text-green-400`} />
    case 'failed':
      return <XCircle className={`${sizeClass} text-red-400`} />
    case 'cancelled':
      return <Ban className={`${sizeClass} text-gray-400`} />
    case 'cancelling':
      return <Loader2 className={`${sizeClass} text-yellow-400 animate-spin`} />
    case 'pending':
      return <Clock className={`${sizeClass} text-gray-500`} />
    case 'quick_ready':
      return <Zap className={`${sizeClass} text-yellow-400`} />
    case 'refining':
    case 'merging':
      return <RefreshCw className={`${sizeClass} text-purple-400 animate-spin`} />
    default:
      return <Loader2 className={`${sizeClass} text-indigo-400 animate-spin`} />
  }
}

/**
 * Get the tailwind background color class for a job status
 */
export function getStatusColor(status: string): string {
  switch (status) {
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
    case 'compressing':
      return 'bg-cyan-500'
    case 'transcribing':
    case 'transcribing_fast':
      return 'bg-purple-500'
    case 'summarizing':
      return 'bg-indigo-500'
    case 'quick_ready':
      return 'bg-yellow-500'
    case 'refining':
    case 'merging':
      return 'bg-purple-500'
    case 'fetching':
      return 'bg-cyan-500'
    case 'pending':
      return 'bg-gray-500'
    default:
      return 'bg-gray-500'
  }
}

/**
 * Get the display text for a job status
 */
export function getStatusText(status: string): string {
  switch (status) {
    case 'pending':
      return 'Waiting...'
    case 'fetching':
      return 'Fetching info...'
    case 'downloading':
      return 'Downloading audio...'
    case 'compressing':
      return 'Creating fast version...'
    case 'transcribing':
      return 'Transcribing...'
    case 'transcribing_fast':
      return 'Fast transcription...'
    case 'summarizing':
      return 'Summarizing...'
    case 'quick_ready':
      return 'Quick summary ready!'
    case 'refining':
      return 'Refining with full audio...'
    case 'merging':
      return 'Finalizing results...'
    case 'completed':
      return 'Done!'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    case 'cancelling':
      return 'Cancelling (after current step)...'
    default:
      return status
  }
}

/**
 * Check if a job status is considered "active" (still processing)
 */
export function isActiveStatus(status: string): boolean {
  return !['completed', 'failed', 'cancelled'].includes(status)
}
