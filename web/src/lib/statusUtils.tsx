/**
 * Shared status utilities for processing jobs
 */
import { Loader2, CheckCircle, XCircle, Clock, Ban, LockKeyhole } from 'lucide-react'

export type JobStatus = 
  | 'pending' 
  | 'fetching'
  | 'downloading' 
  | 'transcribing' 
  | 'summarizing' 
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
    case 'success':
    case 'completed':
      return <CheckCircle className={`${sizeClass} text-green-400`} />
    case 'failed':
      return <XCircle className={`${sizeClass} text-red-400`} />
    case 'restricted':
      return <LockKeyhole className={`${sizeClass} text-amber-300`} />
    case 'cancelled':
      return <Ban className={`${sizeClass} text-gray-400`} />
    case 'cancelling':
      return <Loader2 className={`${sizeClass} text-yellow-400 animate-spin`} />
    case 'pending':
      return <Clock className={`${sizeClass} text-gray-500`} />
    default:
      return <Loader2 className={`${sizeClass} text-indigo-400 animate-spin`} />
  }
}

/**
 * Get the tailwind background color class for a job status
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
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
    case 'saving':
    case 'parsing':
    case 'summarizing':
      return 'bg-indigo-500'
    case 'fetching':
      return 'bg-cyan-500'
    case 'pending':
      return 'bg-gray-500'
    default:
      return 'bg-indigo-500'
  }
}

/**
 * Get the display text for a job status
 */
export function getStatusText(status: string): string {
  switch (status) {
    case 'restricted':
      return 'Source access required'
    case 'pending':
      return 'Queued'
    case 'fetching':
      return 'Fetching info...'
    case 'downloading':
      return 'Downloading...'
    case 'transcribing':
      return 'Transcribing...'
    case 'saving':
      return 'Saving and verifying'
    case 'parsing':
      return 'Reading source'
    case 'summarizing':
      return 'Generating summary'
    case 'success':
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    case 'cancelling':
      return 'Cancelling...'
    default:
      return 'Processing...'
  }
}

/**
 * Check if a job status is considered "active" (still processing)
 */
export function isActiveStatus(status: string): boolean {
  return !['completed', 'success', 'failed', 'cancelled', 'discovered', 'restricted'].includes(status)
}
