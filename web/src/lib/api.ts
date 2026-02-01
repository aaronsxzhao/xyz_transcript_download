/**
 * API client for backend communication
 */

import { getAccessToken } from './auth'

const API_BASE = '/api'

/**
 * Helper to create headers with auth token
 */
function getAuthHeaders(contentType?: string): HeadersInit {
  const headers: HeadersInit = {}
  
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  if (contentType) {
    headers['Content-Type'] = contentType
  }
  
  return headers
}

/**
 * Authenticated fetch wrapper
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  }
  
  return fetch(url, { ...options, headers })
}

export interface Podcast {
  pid: string
  title: string
  author: string
  description: string
  cover_url: string
  episode_count: number
  summarized_count: number
}

export interface Episode {
  eid: string
  pid: string
  title: string
  description: string
  duration: number
  pub_date: string
  cover_url: string
  audio_url: string
  status: string
  has_transcript: boolean
  has_summary: boolean
}

export interface Summary {
  episode_id: string
  title: string
  overview: string
  key_points: KeyPoint[]
  topics: string[]
  takeaways: string[]
}

export interface KeyPoint {
  topic: string
  summary: string
  original_quote: string
  timestamp: string
}

export interface Transcript {
  episode_id: string
  language: string
  duration: number
  text: string
  segments: TranscriptSegment[]
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
}

export interface Stats {
  total_podcasts: number
  total_episodes: number
  total_transcripts: number
  total_summaries: number
  processing_queue: number
}

export interface SummaryListItem {
  episode_id: string
  title: string
  topics_count: number
  key_points_count: number
}

export interface ProcessingJob {
  job_id: string
  status: string
  progress: number
  message: string
  episode_id?: string
  episode_title?: string
}

// API functions
export async function fetchStats(): Promise<Stats> {
  const res = await authFetch(`${API_BASE}/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export async function fetchPodcasts(): Promise<Podcast[]> {
  const res = await authFetch(`${API_BASE}/podcasts`)
  if (!res.ok) throw new Error('Failed to fetch podcasts')
  return res.json()
}

export async function addPodcast(url: string): Promise<Podcast> {
  const res = await authFetch(`${API_BASE}/podcasts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to add podcast')
  }
  return res.json()
}

export async function removePodcast(pid: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/podcasts/${pid}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to remove podcast')
}

export async function fetchPodcast(pid: string): Promise<Podcast> {
  const res = await authFetch(`${API_BASE}/podcasts/${pid}`)
  if (!res.ok) throw new Error('Failed to fetch podcast')
  return res.json()
}

export async function fetchEpisodes(pid: string): Promise<Episode[]> {
  const res = await authFetch(`${API_BASE}/podcasts/${pid}/episodes`)
  if (!res.ok) throw new Error('Failed to fetch episodes')
  return res.json()
}

export async function fetchSummaries(): Promise<SummaryListItem[]> {
  const res = await authFetch(`${API_BASE}/summaries`)
  if (!res.ok) throw new Error('Failed to fetch summaries')
  return res.json()
}

export async function fetchSummary(eid: string): Promise<Summary> {
  const res = await authFetch(`${API_BASE}/summaries/${eid}`)
  if (!res.ok) throw new Error('Failed to fetch summary')
  return res.json()
}

export async function fetchTranscript(eid: string): Promise<Transcript> {
  const res = await authFetch(`${API_BASE}/transcripts/${eid}`)
  if (!res.ok) throw new Error('Failed to fetch transcript')
  return res.json()
}

export async function processEpisode(
  episodeUrl: string,
  options: { transcribeOnly?: boolean; force?: boolean } = {}
): Promise<{ job_id: string; episode_id?: string; episode_title?: string }> {
  const modelSettings = getUserModelSettings()
  const res = await authFetch(`${API_BASE}/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      episode_url: episodeUrl,
      transcribe_only: options.transcribeOnly || false,
      force: options.force || false,
      whisper_model: modelSettings.whisper_model,
      llm_model: modelSettings.llm_model,
    }),
  })
  if (!res.ok) throw new Error('Failed to start processing')
  return res.json()
}

export async function refreshPodcast(pid: string): Promise<{ message: string; total: number }> {
  const res = await authFetch(`${API_BASE}/podcasts/${pid}/refresh`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to refresh podcast')
  return res.json()
}

export async function fetchSettings(): Promise<{
  whisper_mode: string
  whisper_model: string
  whisper_backend: string
  whisper_device: string
  llm_model: string
  check_interval: number
}> {
  const res = await authFetch(`${API_BASE}/settings`)
  if (!res.ok) throw new Error('Failed to fetch settings')
  return res.json()
}

export async function updateSettings(settings: {
  whisper_model?: string
  llm_model?: string
}): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!res.ok) throw new Error('Failed to update settings')
  return res.json()
}

/**
 * Get user's selected models from localStorage
 * Used by processing functions to pass to API
 */
export function getUserModelSettings(): { whisper_model: string; llm_model: string } {
  return {
    whisper_model: localStorage.getItem('whisper_model') || 'whisper-large-v3-turbo',
    llm_model: localStorage.getItem('llm_model') || 'openrouter/openai/gpt-4o',
  }
}

export async function cancelJob(jobId: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to cancel job')
  return res.json()
}

export async function deleteJob(jobId: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/jobs/${jobId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete job')
  return res.json()
}

export async function retryJob(jobId: string): Promise<{ message: string; new_job_id: string }> {
  const res = await authFetch(`${API_BASE}/jobs/${jobId}/retry`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to retry job')
  return res.json()
}

export async function resummarizeEpisode(episodeId: string): Promise<{ message: string; job_id: string }> {
  const modelSettings = getUserModelSettings()
  const res = await authFetch(`${API_BASE}/episodes/${episodeId}/resummarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      llm_model: modelSettings.llm_model,
    }),
  })
  if (!res.ok) throw new Error('Failed to start re-summarization')
  return res.json()
}

export async function deleteEpisode(eid: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/episodes/${eid}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete episode')
  return res.json()
}
