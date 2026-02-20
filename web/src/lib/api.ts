/**
 * API client for backend communication
 */

import { getAccessToken, refreshToken } from './auth'

const API_BASE = '/api'

/**
 * Helper to create headers with auth token
 */
function getAuthHeaders(token?: string | null, contentType?: string): HeadersInit {
  const headers: HeadersInit = {}
  
  const t = token ?? getAccessToken()
  if (t) {
    headers['Authorization'] = `Bearer ${t}`
  }
  
  if (contentType) {
    headers['Content-Type'] = contentType
  }
  
  return headers
}

/**
 * Authenticated fetch wrapper with automatic token refresh on 401.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  }
  
  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    const tokens = await refreshToken()
    if (tokens) {
      const retryHeaders = {
        ...getAuthHeaders(tokens.access_token),
        ...options.headers,
      }
      return fetch(url, { ...options, headers: retryHeaders })
    }
  }

  return res
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
  topics_count: number
  key_points_count: number
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
      max_output_tokens: modelSettings.max_output_tokens,
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
  max_output_tokens?: number
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
export function getUserModelSettings(): { 
  whisper_model: string
  llm_model: string
  max_output_tokens: number 
} {
  const savedTokens = localStorage.getItem('max_output_tokens')
  return {
    whisper_model: localStorage.getItem('whisper_model') || 'whisper-large-v3-turbo',
    llm_model: localStorage.getItem('llm_model') || '',
    max_output_tokens: savedTokens ? parseInt(savedTokens, 10) : 16000,
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
      max_output_tokens: modelSettings.max_output_tokens,
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

export interface NewEpisode {
  eid: string
  title: string
  podcast_title: string
  podcast_pid: string
}

export interface NewEpisodesResponse {
  episodes: NewEpisode[]
  last_check: string | null
}

export async function fetchNewEpisodes(): Promise<NewEpisodesResponse> {
  const res = await authFetch(`${API_BASE}/new-episodes`)
  if (!res.ok) throw new Error('Failed to fetch new episodes')
  return res.json()
}

export async function checkPodcastsForUpdates(): Promise<{
  message: string
  new_episodes: number
  episodes: NewEpisode[]
}> {
  const res = await authFetch(`${API_BASE}/check-podcasts`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to check for updates')
  return res.json()
}

export interface ImportSubscriptionsResult {
  total_found: number
  newly_added: number
  already_subscribed: number
  failed: number
  podcasts: string[]
}

export async function importUserSubscriptions(username: string): Promise<ImportSubscriptionsResult> {
  const res = await authFetch(`${API_BASE}/podcasts/import-subscriptions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to import subscriptions')
  }
  return res.json()
}


// ===== Video Notes API =====

export interface VideoTask {
  id: string
  url: string
  platform: string
  title: string
  thumbnail: string
  status: string
  progress: number
  message: string
  markdown: string
  transcript: { text: string; segments: { start: number; end: number; text: string }[]; duration: number } | null
  style: string
  model: string
  formats: string[]
  quality: string
  extras: string
  video_understanding: boolean
  video_interval: number
  grid_cols: number
  grid_rows: number
  duration: number
  error: string
  created_at: string
  updated_at: string
  versions?: VideoTaskVersion[]
}

export interface VideoTaskVersion {
  id: string
  task_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface VideoNoteRequest {
  url: string
  platform?: string
  style?: string
  formats?: string[]
  quality?: string
  video_quality?: string
  llm_model?: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  grid_cols?: number
  grid_rows?: number
  max_output_tokens?: number
}

export async function generateVideoNote(data: VideoNoteRequest): Promise<{ task_id: string }> {
  const modelSettings = getUserModelSettings()
  const res = await authFetch(`${API_BASE}/video-notes/generate-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...data,
      llm_model: data.llm_model || modelSettings.llm_model,
      max_output_tokens: data.max_output_tokens || modelSettings.max_output_tokens,
    }),
  })
  if (!res.ok) {
    let detail = `Server error ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.message || detail
    } catch { /* ignore parse errors */ }
    throw new Error(detail)
  }
  return res.json()
}

export async function fetchVideoTasks(): Promise<{ tasks: VideoTask[] }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks`)
  if (!res.ok) throw new Error('Failed to fetch video tasks')
  return res.json()
}

export async function fetchVideoTask(taskId: string): Promise<VideoTask> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}`)
  if (!res.ok) throw new Error('Failed to fetch video task')
  return res.json()
}

export async function deleteVideoTask(taskId: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete video task')
  return res.json()
}

export async function retryVideoTask(taskId: string): Promise<{ task_id: string }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}/retry`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to retry video task')
  return res.json()
}

export async function cancelVideoTask(taskId: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to cancel video task')
  return res.json()
}

export async function uploadVideoFile(file: File): Promise<{ file_id: string; path: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authFetch(`${API_BASE}/video-notes/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error('Failed to upload video')
  return res.json()
}

export async function fetchVideoNoteStyles(): Promise<{ styles: Record<string, string> }> {
  const res = await authFetch(`${API_BASE}/video-notes/styles`)
  if (!res.ok) throw new Error('Failed to fetch styles')
  return res.json()
}

export async function fetchSysHealth(): Promise<{
  ffmpeg: { available: boolean; version?: string; error?: string }
  ytdlp: { available: boolean; version?: string; error?: string }
}> {
  const res = await authFetch(`${API_BASE}/video-notes/sys-health`)
  if (!res.ok) throw new Error('Failed to fetch system health')
  return res.json()
}

// ===== Cookie Management API =====

export async function fetchCookieStatus(platform: string): Promise<{ platform: string; has_cookie: boolean }> {
  const res = await authFetch(`${API_BASE}/cookies/${platform}`)
  if (!res.ok) throw new Error('Failed to fetch cookie status')
  return res.json()
}

export async function validateBilibiliCookie(): Promise<{ valid: boolean; reason: string; message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/bilibili/validate`)
  if (!res.ok) return { valid: false, reason: 'error', message: 'Server error' }
  return res.json()
}

export async function updateCookie(platform: string, cookieData: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/cookies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, cookie_data: cookieData }),
  })
  if (!res.ok) throw new Error('Failed to update cookie')
  return res.json()
}

export async function fetchAllCookies(): Promise<{ cookies: { platform: string; has_cookie: boolean; updated_at: string }[] }> {
  const res = await authFetch(`${API_BASE}/cookies`)
  if (!res.ok) throw new Error('Failed to fetch cookies')
  return res.json()
}

export async function bilibiliQrGenerate(): Promise<{ qr_url: string; qrcode_key: string }> {
  const res = await authFetch(`${API_BASE}/cookies/bilibili/qr/generate`)
  if (!res.ok) throw new Error('Failed to generate QR code')
  return res.json()
}

export async function bilibiliQrPoll(qrcodeKey: string): Promise<{ status: string; message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/bilibili/qr/poll?qrcode_key=${encodeURIComponent(qrcodeKey)}`)
  if (!res.ok) throw new Error('Failed to poll QR status')
  return res.json()
}

export async function douyinQrGenerate(): Promise<{ qr_url: string; token: string }> {
  const res = await authFetch(`${API_BASE}/cookies/douyin/qr/generate`)
  if (!res.ok) throw new Error('Failed to generate Douyin QR code')
  return res.json()
}

export async function douyinQrPoll(token: string): Promise<{ status: string; message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/douyin/qr/poll?token=${encodeURIComponent(token)}`)
  if (!res.ok) throw new Error('Failed to poll Douyin QR status')
  return res.json()
}

export async function saveSimpleCookie(platform: string, cookieString: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/save-simple`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, cookie_string: cookieString }),
  })
  if (!res.ok) throw new Error('Failed to save cookie')
  return res.json()
}

export async function uploadCookieFile(platform: string, file: File): Promise<{ message: string; cookie_count: number }> {
  const form = new FormData()
  form.append('platform', platform)
  form.append('file', file)
  const res = await authFetch(`${API_BASE}/cookies/upload-file`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(err.detail || 'Failed to upload cookie file')
  }
  return res.json()
}
