import { bufferResponse, requestWithDeadline } from './requestDeadline'
/**
 * API client for backend communication
 */

import { getAccessToken, getAuthGeneration, getRefreshToken, accessTokenNeedsRefresh, refreshToken } from './auth'
import { getAccountId, getPreference, setPreference } from './preferences'
import { CacheKeys, getCache, setCache, invalidateForMutation } from './cache'

import { takeStartupRead } from './startupReads'

const API_BASE = '/api'
const UNKNOWN_CHANNEL_SENTINEL = '__unknown__'
const pendingReads = new Map<string, Promise<unknown>>()
let readRevision = 0
export function getReadRevision() { return readRevision }

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message) }
}

function assertSessionGeneration(generation: number): void {
  if (generation !== getAuthGeneration()) throw new DOMException('Account changed', 'AbortError')
}

function readJson<T>(url: string, operation: string, signal?: AbortSignal): Promise<T> {
  const generation = getAuthGeneration()
  const key = `${generation}:${url}`
  const existing = pendingReads.get(key)
  if (existing && !signal) return existing as Promise<T>
  const request = requestWithDeadline(async controllerSignal => {
    assertSessionGeneration(generation)
    return authFetch(url, { signal: controllerSignal }).then(response => parseApiResponseAsJson<T>(response, operation)).then(data => {
      assertSessionGeneration(generation)
      return data
    })
  }, {signal, retry:true},
  ).finally(() => {
    if (pendingReads.get(key) === request) pendingReads.delete(key)
  })
  if (!signal) pendingReads.set(key, request)
  return request
}

/** Dev-only visibility for swallowed parse errors (non-fatal fallbacks). */
function logIgnoredJsonError(context: string, err: unknown): void {
  if (import.meta.env.DEV) {
    console.debug(`[api] ${context}:`, err)
  }
}

function detailFromApiBody(body: unknown): string | undefined {
  if (body === null || typeof body !== 'object') return undefined
  const o = body as Record<string, unknown>
  if (typeof o.detail === 'string') return o.detail
  if (Array.isArray(o.detail)) {
    try {
      return JSON.stringify(o.detail)
    } catch {
      return String(o.detail)
    }
  }
  if (typeof o.message === 'string') return o.message
  return undefined
}

/**
 * Read JSON from a fetch Response once. Proxies sometimes return 5xx plain text;
 * this surfaces that text instead of a cryptic JSON.parse error.
 */
export async function parseApiResponseAsJson<T>(res: Response, operation: string): Promise<T> {
  const text = await res.text()
  let body: unknown
  try {
    body = text.trim() ? JSON.parse(text) : null
  } catch {
    const snippet = text.slice(0, 240).replace(/\s+/g, ' ').trim()
    if (!res.ok) {
      throw new ApiError(
        `${operation} (${res.status}): ${snippet || 'non-JSON error response (check server / reverse proxy logs)'}`,
        res.status,
      )
    }
    throw new Error(`${operation}: invalid JSON — ${snippet.slice(0, 120)}…`)
  }

  if (!res.ok) {
    const msg = detailFromApiBody(body) || `${operation} (${res.status})`
    throw new ApiError(msg, res.status)
  }

  if (body === null || body === undefined) {
    throw new Error(`${operation}: empty response body (${res.status})`)
  }

  return body as T
}

/**
 * Authenticated fetch wrapper with automatic token refresh on 401.
 */
/** Shared deadline covers authentication, headers and body; mutations are never auto-retried on timeout. */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  if (options.signal) return performAuthFetch(url, options)
  const mutation = !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())
  const generation = getAuthGeneration()
  return requestWithDeadline(async signal => {
    assertSessionGeneration(generation)
    return performAuthFetch(url, {...options, signal}).then(bufferResponse).then(response => {
      assertSessionGeneration(generation)
      return response
    })
  }, {
    timeout:mutation ? 60000 : 15000, retry:!mutation,
    message:mutation ? 'No confirmation received. The operation may still be running. Check its status before submitting again.' : undefined,
  })
}

async function performAuthFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const ownerGeneration = getAuthGeneration()
  const headers = new Headers(options.headers)
  let token = getAccessToken()
  if (accessTokenNeedsRefresh(token) && getRefreshToken()) {
    token = (await refreshToken())?.access_token || null
    assertSessionGeneration(ownerGeneration)
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const mutating = !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())
  if (mutating) { readRevision += 1; pendingReads.clear() }
  
  const pendingStartup = (options.method || 'GET').toUpperCase() === 'GET' && !options.body ? takeStartupRead(url, token) : null
  const early = pendingStartup ? await pendingStartup : null
  assertSessionGeneration(ownerGeneration)
  const res = early || await fetch(url, { ...options, headers })
  assertSessionGeneration(ownerGeneration)
  if (mutating && res.ok) invalidateForMutation(url)

  if (res.status === 401) {
    const tokens = await refreshToken()
    if (tokens) {
      assertSessionGeneration(ownerGeneration)
      headers.set('Authorization', `Bearer ${tokens.access_token}`)
      const retry = await fetch(url, { ...options, headers })
      assertSessionGeneration(ownerGeneration)
      if (mutating && retry.ok) invalidateForMutation(url)
      return retry
    }
  }

  return res
}

export interface Podcast {
  resolved_episode_id?: string | null
  resolved_episode_title?: string | null
  pid: string
  title: string
  author: string
  description: string
  cover_url: string
  episode_count: number
  summarized_count: number
  platform: string
  feed_url: string
  episode_preview?: Episode[]
}

export interface Episode {
  source_status?: string
  source_message?: string
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
  quality_status?: "ready" | "needs_review" | "not_processed"
  has_summary: boolean
  topics_count: number
  key_points_count: number
  created_at: string
}

export interface LocalAudioUploadResult {
  podcast: Podcast
  episode: Episode
}

const CHUNKED_AUDIO_UPLOAD_THRESHOLD = 8 * 1024 * 1024

export interface Summary {
  quality_warning?: string
  source_status?: string
  source_message?: string
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
  total_videos: number
  completed_videos: number
  total_video_channels: number
}

export interface SummaryListItem {
  episode_id: string
  title: string
  topics_count: number
  key_points_count: number
  podcast_title: string
  podcast_cover: string
  created_at: string
}

export interface ProcessingJob {
  revision?: number
  started_at?: number
  job_id: string
  status: string
  progress: number
  message: string
  episode_id?: string
  episode_title?: string
}

export async function fetchJob(jobId: string): Promise<ProcessingJob> {
  return parseApiResponseAsJson(await authFetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`), 'Cannot load processing status')
}

// API functions
export async function fetchStats(): Promise<Stats> {
  return readJson(`${API_BASE}/stats`, 'Cannot load statistics')
}

export function fetchProgress(known: string[]): Promise<{tasks: VideoTask[]}> {
  return readJson(`${API_BASE}/video-notes/progress?${new URLSearchParams({known:known.slice(0,100).join(',')})}`, 'Cannot refresh progress')
}

export async function fetchPodcasts(): Promise<Podcast[]> {
  const owner=getAccountId(), revision=getReadRevision()
  const rows=await readJson<Podcast[]>(`${API_BASE}/podcasts?include_content=12`, 'Failed to fetch podcasts')
  const podcasts=rows.map(({episode_preview,...podcast})=>{
    if(episode_preview && owner===getAccountId() && revision===getReadRevision()) {
      const key=CacheKeys.EPISODES(podcast.pid),existing=getCache<Episode[]>(key)
      const aligned=existing && episode_preview.every((ep,i)=>existing[i]?.eid===ep.eid)
      setCache(key,aligned?[...episode_preview,...existing.slice(episode_preview.length)]:episode_preview,owner)
    }
    return podcast
  })
  if(owner===getAccountId() && revision===getReadRevision())setCache(CacheKeys.PODCASTS,podcasts,owner)
  return podcasts
}

export async function addPodcast(url: string): Promise<Podcast> {
  const res = await authFetch(`${API_BASE}/podcasts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  return parseApiResponseAsJson<Podcast>(res, 'Failed to add podcast')
}

export async function uploadLocalPodcastAudio(
  file: File,
  options: { title?: string; description?: string } = {}
): Promise<LocalAudioUploadResult> {
  const generation = getAuthGeneration()
  if (file.size > CHUNKED_AUDIO_UPLOAD_THRESHOLD) {
    return uploadLocalPodcastAudioChunked(file, options)
  }

  let res: Response
  try {
    const formData = new FormData()
    formData.append('file', file)
    if (options.title) formData.append('title', options.title)
    if (options.description) formData.append('description', options.description)

    res = await authFetch(`${API_BASE}/podcasts/upload-audio`, {
      method: 'POST',
      body: formData,
    })
  } catch (error) {
    assertSessionGeneration(generation)
    if (isNetworkOrTimeoutError(error)) {
      // This endpoint creates an episode. Losing the response does not prove
      // the save failed, so replaying it as a new chunked upload can duplicate it.
      throw new Error('Upload confirmation was lost. Check Local Uploads before uploading this audio again.')
    }
    throw error
  }
  assertSessionGeneration(generation)
  if (res.status === 413) {
    return uploadLocalPodcastAudioChunked(file, options)
  }
  if (!res.ok) {
    throw new Error(await parseLocalAudioUploadError(res))
  }
  const result = await res.json()
  assertSessionGeneration(generation)
  return result
}

async function parseLocalAudioUploadError(res: Response): Promise<string> {
  let detail = 'Failed to upload audio'
  const text = await res.text().catch(() => '')
  if (text.trim()) {
    try {
      const body = JSON.parse(text) as { detail?: string; message?: string }
      detail = body.detail || body.message || detail
    } catch {
      detail = humanizeHtmlOrCdnError(text, res.status)
    }
  }

  if (detail !== 'Failed to upload audio' && /<!DOCTYPE|<html/i.test(detail)) {
    detail = humanizeHtmlOrCdnError(detail, res.status)
  }

  if (res.status === 413) {
    return 'This upload was blocked before it reached the app. The hosted site has per-request upload limits, so larger audio files are now sent in chunks. Please retry after refreshing the page.'
  }

  return detail
}

async function uploadLocalPodcastAudioChunked(
  file: File,
  options: { title?: string; description?: string } = {}
): Promise<LocalAudioUploadResult> {
  const generation = getAuthGeneration()
  const initData = new FormData()
  initData.append('filename', file.name)
  initData.append('size', String(file.size))

  const initRes = await authFetch(`${API_BASE}/podcasts/upload-audio/init`, {
    method: 'POST',
    body: initData,
  })
  if (!initRes.ok) {
    throw new Error(await parseLocalAudioUploadError(initRes))
  }

  const init = await initRes.json() as {
    upload_id: string
    chunk_size: number
    total_chunks: number
  }
  assertSessionGeneration(generation)

  for (let index = 0; index < init.total_chunks; index += 1) {
    const start = index * init.chunk_size
    const end = Math.min(file.size, start + init.chunk_size)

    for (let attempt = 0; attempt <= CHUNK_RETRY_ATTEMPTS; attempt++) {
      assertSessionGeneration(generation)
      try {
        const chunkData = new FormData()
        chunkData.append('upload_id', init.upload_id)
        chunkData.append('index', String(index))
        chunkData.append('chunk', file.slice(start, end), `${file.name}.part-${index}`)

        const chunkRes = await authFetchWithTimeout(
          `${API_BASE}/podcasts/upload-audio/chunk`,
          { method: 'POST', body: chunkData },
          CHUNK_UPLOAD_TIMEOUT_MS,
        )
        assertSessionGeneration(generation)
        if (!chunkRes.ok) {
          const canRetry = attempt < CHUNK_RETRY_ATTEMPTS && shouldRetryVideoUploadAsChunked(chunkRes.status)
          if (canRetry) {
            await sleep(CHUNK_RETRY_BASE_MS * 2 ** attempt)
            continue
          }
          throw new Error(await parseLocalAudioUploadError(chunkRes))
        }
        break
      } catch (error) {
        assertSessionGeneration(generation)
        if (isNetworkOrTimeoutError(error) && attempt < CHUNK_RETRY_ATTEMPTS) {
          await sleep(CHUNK_RETRY_BASE_MS * 2 ** attempt)
          continue
        }
        throw error
      }
    }
  }

  const completeData = new FormData()
  completeData.append('upload_id', init.upload_id)
  if (options.title) completeData.append('title', options.title)
  if (options.description) completeData.append('description', options.description)

  assertSessionGeneration(generation)
  const completeRes = await authFetch(`${API_BASE}/podcasts/upload-audio/complete`, {
    method: 'POST',
    body: completeData,
  })
  if (!completeRes.ok) {
    throw new Error(await parseLocalAudioUploadError(completeRes))
  }

  const result = await completeRes.json()
  assertSessionGeneration(generation)
  return result
}

export async function removePodcast(pid: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/podcasts/${pid}`, {
    method: 'DELETE',
  })
  if (!res.ok) await parseApiResponseAsJson(res, 'Failed to remove podcast')
}

export async function fetchPodcast(pid: string): Promise<Podcast> {
  return readJson(`${API_BASE}/podcasts/${pid}`, 'Failed to fetch podcast')
}

export async function fetchEpisodes(pid: string, offset = 0, limit = 50): Promise<Episode[]> {
  return readJson(`${API_BASE}/podcasts/content?pid=${encodeURIComponent(pid)}&offset=${offset}&limit=${limit}`, 'Failed to fetch episodes')
}

export async function fetchEpisode(eid: string): Promise<Episode> {
  return parseApiResponseAsJson(await authFetch(`${API_BASE}/episodes/${encodeURIComponent(eid)}`), 'Cannot load episode')
}

export async function fetchSummaries(): Promise<SummaryListItem[]> {
  return readJson(`${API_BASE}/summaries`, 'Failed to fetch summaries')
}

export async function fetchRecentSummaries(limit: number = 6): Promise<SummaryListItem[]> {
  const res = await authFetch(`${API_BASE}/summaries/recent?limit=${encodeURIComponent(String(limit))}`)
  if (!res.ok) throw new Error('Failed to fetch recent summaries')
  return res.json()
}

export async function fetchSummary(eid: string): Promise<Summary> {
  return readJson(`${API_BASE}/summaries/${eid}`, 'Failed to fetch summary')
}

export async function fetchTranscript(eid: string): Promise<Transcript> {
  return readJson(`${API_BASE}/transcripts/${eid}`, 'Failed to fetch transcript')
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
  return parseApiResponseAsJson<{ job_id: string; episode_id?: string; episode_title?: string }>(
    res,
    'Failed to start processing',
  )
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
  llm_provider: 'server' | 'groq' | 'custom'
  transcription_provider: 'server' | 'custom'
  llm_base_url: string
  whisper_base_url: string
  llm_key_saved: boolean
  whisper_key_saved: boolean
  groq_available: boolean
  llm_configured: boolean
  whisper_provider: string
  check_interval: number
}> {
  return readJson(`${API_BASE}/settings`, 'Cannot load settings. Please retry.')
}

export async function updateSettings(settings: {
  whisper_model?: string
  llm_model?: string
  llm_provider?: 'server' | 'groq' | 'custom'
  transcription_provider?: 'server' | 'custom'
  llm_base_url?: string
  whisper_base_url?: string
  llm_api_key?: string
  whisper_api_key?: string
}): Promise<{ message: string; settings?: Awaited<ReturnType<typeof fetchSettings>> }> {
  const res = await authFetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  return parseApiResponseAsJson(res, 'Failed to update settings')
}

export async function testLlmConnection(settings: { llm_provider: string; llm_model: string; llm_base_url?:string; llm_api_key?:string }): Promise<{ message: string; model: string }> {
  return parseApiResponseAsJson(await authFetch(`${API_BASE}/settings/test-llm`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }), 'Summary connection failed')
}

/**
 * Get user's selected models from localStorage
 * Used by processing functions to pass to API
 */
export function getUserModelSettings(): { 
  whisper_model: string
  llm_model: string
} {
  return {
    whisper_model: getPreference('whisper_model') || '',
    llm_model: getPreference('llm_model') || '',
  }
}

export async function cancelJob(jobId: string): Promise<{ message: string; status?: string }> {
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
  return parseApiResponseAsJson(res, 'Failed to delete episode')
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

export async function checkVideoChannelsForUpdates(opts?: {
  channel?: string
  platform?: string
}): Promise<{
  message: string
  new_videos: number
  channels_checked: number
}> {
  const params = new URLSearchParams()
  if (opts?.channel) params.set('channel', opts.channel)
  if (opts?.platform) params.set('platform', opts.platform)
  const qs = params.toString()
  const defaults = getVideoProcessingDefaults()
  const hasBody = Object.keys(defaults).length > 0
  const res = await authFetch(`${API_BASE}/video-notes/check-channels${qs ? `?${qs}` : ''}`, {
    method: 'POST',
    headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
    body: hasBody ? JSON.stringify(defaults) : undefined,
  })
  if (!res.ok) throw new Error('Failed to check video channels')
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
  started_at?: number
  id: string
  url: string
  platform: string
  title: string
  thumbnail: string
  channel: string
  channel_url: string
  channel_avatar: string
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
  published_at: string
  created_at: string
  updated_at: string
  versions?: Omit<VideoTaskVersion, 'content'>[]
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
  skip_existing?: boolean
  url: string
  title?: string
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
}

export async function generateVideoNote(data: VideoNoteRequest): Promise<{ task_id: string; skipped?: boolean }> {
  const modelSettings = getUserModelSettings()
  const generation = getAuthGeneration()
  let res: Response
  try {
    res = await authFetch(`${API_BASE}/video-notes/generate-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...data,
      llm_model: data.llm_model || modelSettings.llm_model,
    }),
    })
  } catch (error) {
    // Favorites use skip_existing: only reconcile this non-destructive import.
    // Never replay a timed-out POST or start a second worker automatically.
    if (data.skip_existing && generation === getAuthGeneration() && !(error instanceof DOMException && error.name === 'AbortError')) {
      try {
        const query = new URLSearchParams({url:data.url, platform:data.platform || ''})
        const found = await readJson<{task_id:string|null;status?:string}>(`${API_BASE}/video-notes/submission?${query}`, 'Cannot confirm submission')
        if (found.task_id && generation === getAuthGeneration()) {
          return {task_id:found.task_id, ...(['failed','cancelled'].includes(found.status || '') ? {skipped:true} : {})}
        }
      } catch { /* Keep the original ambiguous error; no mutation retry. */ }
    }
    throw error
  }
  const parsed = await parseApiResponseAsJson<{ task_id?: string; skipped?: boolean }>(
    res,
    'Video note request failed',
  )
  if (typeof parsed.task_id !== 'string' || !parsed.task_id.trim()) {
    throw new Error('Video note request failed: server response missing task_id')
  }
  return { task_id: parsed.task_id, ...(parsed.skipped ? {skipped:true} : {}) }
}

export async function fetchVideoTasks(): Promise<{ tasks: VideoTask[] }> {
  return readJson(`${API_BASE}/video-notes/tasks`, 'Failed to fetch video tasks')
}

export interface VideoChannelStat {
  channel: string
  platform: string
  channel_url: string
  channel_avatar: string
  thumbnail: string
  total: number
  done: number
  last_updated: string
}

export async function fetchVideoChannels(): Promise<{ channels: VideoChannelStat[] }> {
  return readJson(`${API_BASE}/video-notes/channels`, 'Cannot load video channels. Please retry.')
}

export async function fetchVideoTasksByChannel(platform: string, channel: string, options: {cursor?:string;q?:string;status?:string;sort?:string;signal?:AbortSignal} = {}): Promise<{ tasks: VideoTask[]; next_cursor: string | null }> {
  const params = new URLSearchParams({ platform, channel })
  for (const key of ['cursor','q','status','sort'] as const) if (options[key] && !(key === 'sort' && options[key] === 'newest')) params.set(key, options[key]!)
  return readJson(`${API_BASE}/video-notes/tasks/by-channel?${params}`, 'Cannot load channel videos. Please retry.', options.signal)
}

export async function fetchRecentVideoTasks(limit: number = 6): Promise<{ tasks: VideoTask[] }> {
  const res = await authFetch(`${API_BASE}/video-notes/recent?limit=${encodeURIComponent(String(limit))}`)
  if (!res.ok) throw new Error('Failed to fetch recent video tasks')
  return res.json()
}

export async function fetchVideoTask(taskId: string): Promise<VideoTask> {
  return readJson(`${API_BASE}/video-notes/tasks/${encodeURIComponent(taskId)}?view=note`, 'Cannot load video notes. Please retry.')
}

export async function fetchVideoTranscript(taskId: string, signal?: AbortSignal): Promise<{ transcript: VideoTask['transcript'] }> {
  return readJson(`${API_BASE}/video-notes/tasks/${encodeURIComponent(taskId)}/transcript`, 'Cannot load video transcript', signal)
}

export async function fetchVideoVersion(taskId: string, versionId: string, signal?: AbortSignal): Promise<VideoTaskVersion> {
  return readJson(`${API_BASE}/video-notes/tasks/${encodeURIComponent(taskId)}/versions/${encodeURIComponent(versionId)}`, 'Cannot load saved version', signal)
}

export async function deleteVideoTask(taskId: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete video task')
  return res.json()
}

export async function deleteVideoChannel(channelName: string): Promise<{ message: string; deleted: number }> {
  const apiChannelName = channelName === 'Unknown Channel' ? UNKNOWN_CHANNEL_SENTINEL : channelName
  const res = await authFetch(`${API_BASE}/video-notes/channels/${encodeURIComponent(apiChannelName)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete channel')
  return res.json()
}

export function getVideoProcessingDefaults(): Record<string, unknown> {
  const d: Record<string, unknown> = {}
  try {
    const s = getPreference('vd_style'); if (s) d.style = s
    const f = getPreference('vd_formats'); if (f) d.formats = JSON.parse(f)
    const q = getPreference('vd_quality'); if (q) d.quality = q
    const vq = getPreference('vd_video_quality'); if (vq) d.video_quality = vq
    const lm = getPreference('llm_model'); if (lm) d.llm_model = lm
  } catch (e) {
    logIgnoredJsonError('getVideoProcessingDefaults', e)
  }
  return d
}

export async function retryVideoTask(taskId: string): Promise<{ task_id: string }> {
  const defaults = getVideoProcessingDefaults()
  const hasBody = Object.keys(defaults).length > 0
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}/retry`, {
    method: 'POST',
    headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
    body: hasBody ? JSON.stringify(defaults) : undefined,
  })
  if (!res.ok) throw new Error('Failed to retry video task')
  try{const dismissed:string[]=JSON.parse(getPreference('dismissed_tasks')||'[]');setPreference('dismissed_tasks',JSON.stringify(dismissed.filter(key=>key!=='video:'+taskId)));window.dispatchEvent(new Event('xyz:tasks-dismissed'))}catch{}
  return res.json()
}

export async function cancelVideoTask(taskId: string): Promise<{ message: string; status?: string }> {
  const res = await authFetch(`${API_BASE}/video-notes/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to cancel video task')
  return res.json()
}

/** Below this size we still try one-shot upload first; on CDN 5xx / 413 we fall back to chunked. */
const CHUNKED_VIDEO_UPLOAD_THRESHOLD = 8 * 1024 * 1024
const DEFAULT_CHUNKED_VIDEO_UPLOAD_CONCURRENCY = 4
const MAX_CHUNKED_VIDEO_UPLOAD_CONCURRENCY = 6
const VIDEO_UPLOAD_ASSEMBLY_POLL_MS = 1500

export interface VideoUploadStatus {
  upload_id: string
  filename: string
  size: number
  received_bytes: number
  assembled_bytes: number
  received_chunks: number[]
  received_chunks_count: number
  total_chunks: number
  phase: string
  error: string
  path: string
  file_id: string
  last_updated: number
  upload_percent: number
  assemble_percent: number
  percent: number
  status_text: string
  location_label: string
}

export interface VideoUploadProgress {
  uploadId: string
  phase: string
  filename: string
  uploadedBytes: number
  assembledBytes: number
  totalBytes: number
  uploadedChunks: number
  totalChunks: number
  percent: number
  statusText: string
  locationLabel: string
}

class UploadResponseError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'UploadResponseError'
    this.status = status
  }
}

/** Single POST failed at proxy/origin — retry as chunked uploads (smaller requests). */
function shouldRetryVideoUploadAsChunked(status: number): boolean {
  return status === 413 || status === 502 || status === 503 || status === 504 || status === 520
}

function isOversizedUploadStatus(status: number): boolean {
  return status === 413
}

/** Turn Cloudflare/HTML error pages into a short, actionable message. */
function humanizeHtmlOrCdnError(text: string, status: number): string {
  const t = text.trim()
  const lower = t.toLowerCase()
  if (
    lower.includes('<!doctype') ||
    lower.includes('<html') ||
    lower.includes('cloudflare') ||
    /\b520\b/.test(t) ||
    /\b502\b/.test(t) ||
    (lower.includes('web server is down') || lower.includes('unknown error'))
  ) {
    return `Upload failed: hosting/CDN error (HTTP ${status}). The server dropped the connection—often a timeout or body limit on large files. Retrying with chunked upload may help; if it keeps happening, check your host (e.g. Render) logs and timeouts.`
  }
  return t.length > 400 ? `${t.slice(0, 400)}…` : t
}

async function parseUploadError(res: Response, fallback = 'Failed to upload video'): Promise<string> {
  // Read body once: res.json() then res.text() fails — stream is single-use (breaks upload error handling).
  let detail = fallback
  const text = await res.text().catch(() => '')
  if (text.trim()) {
    try {
      const body = JSON.parse(text) as { detail?: string; message?: string }
      detail = body.detail || body.message || detail
    } catch {
      detail = humanizeHtmlOrCdnError(text, res.status)
    }
  }

  if (detail !== fallback && /<!DOCTYPE|<html/i.test(detail)) {
    detail = humanizeHtmlOrCdnError(detail, res.status)
  }

  if (isOversizedUploadStatus(res.status)) {
    return 'This upload was blocked before it reached the app. The hosted site sits behind a proxy with per-request size limits, so large local videos need chunked upload. Please retry after refreshing; the app should now switch large files to chunked upload automatically.'
  }

  return detail
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}


/** Detect network-level failures (connection refused, timeout, DNS, etc.)
 *  that never produce an HTTP status code — the browser throws a TypeError. */
function isNetworkOrTimeoutError(error: unknown): boolean {
  if (error instanceof TypeError) {
    const msg = error.message.toLowerCase()
    return msg.includes('failed to fetch') || msg.includes('network')
  }
  if (error instanceof DOMException && error.name === 'TimeoutError') return true
  return false
}

const CHUNK_RETRY_ATTEMPTS = 3
const CHUNK_RETRY_BASE_MS = 1500
const CHUNK_UPLOAD_TIMEOUT_MS = 45_000

/** Wrapper around authFetch that aborts if the request takes longer than `timeoutMs`. */
async function authFetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout>
  let abort!: () => void
  const deadline = new Promise<never>((_, reject) => {
    abort = () => { controller.abort(); reject(new DOMException('Upload cancelled', 'AbortError')) }
    timer = setTimeout(() => {
      controller.abort()
      reject(new DOMException('Upload connection timed out. Please retry.', 'TimeoutError'))
    }, timeoutMs)
    options.signal?.addEventListener('abort', abort, { once: true })
    if (options.signal?.aborted) abort()
  })
  const request = authFetch(url, { ...options, signal: controller.signal }).then(async response =>
    new Response([204, 205, 304].includes(response.status) ? null : await response.text(), { status: response.status, headers: response.headers }))
  try { return await Promise.race([request, deadline]) }
  finally { clearTimeout(timer!); options.signal?.removeEventListener('abort', abort) }
}

function startAssemblyStatusPolling(
  uploadId: string,
  filename: string,
  onProgress?: (progress: VideoUploadProgress) => void,
): () => void {
  const generation = getAuthGeneration()
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const poll = async () => {
    if (generation !== getAuthGeneration()) { controller.abort(); return }
    try {
      const status = await fetchVideoUploadStatus(uploadId, controller.signal)
      if (!controller.signal.aborted && generation === getAuthGeneration()) onProgress?.(toUploadProgress(status, filename))
    } catch (e) {
      if (!controller.signal.aborted) logIgnoredJsonError('assembly status poll', e)
    }
    if (!controller.signal.aborted && generation === getAuthGeneration()) timer = setTimeout(() => void poll(), VIDEO_UPLOAD_ASSEMBLY_POLL_MS)
  }
  void poll()
  return () => { controller.abort(); clearTimeout(timer) }
}

function toUploadProgress(status: VideoUploadStatus, fallbackName = ''): VideoUploadProgress {
  return {
    uploadId: status.upload_id,
    phase: status.phase,
    filename: status.filename || fallbackName,
    uploadedBytes: status.received_bytes,
    assembledBytes: status.assembled_bytes,
    totalBytes: status.size,
    uploadedChunks: status.received_chunks_count,
    totalChunks: status.total_chunks,
    percent: Math.round(status.percent),
    statusText: status.status_text,
    locationLabel: status.location_label,
  }
}

async function fetchVideoUploadStatus(uploadId: string, signal?: AbortSignal): Promise<VideoUploadStatus> {
  const res = await authFetchWithTimeout(`${API_BASE}/video-notes/upload/status?upload_id=${encodeURIComponent(uploadId)}`, { signal }, 10000)
  if (!res.ok) {
    throw new Error(await parseUploadError(res, 'Failed to fetch upload status'))
  }
  return res.json()
}

async function uploadVideoFileSimple(file: File): Promise<{ file_id: string; path: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await authFetchWithTimeout(`${API_BASE}/video-notes/upload`, {
    method: 'POST',
    body: formData,
  }, 120000)
  if (!res.ok) {
    throw new UploadResponseError(await parseUploadError(res), res.status)
  }
  return res.json()
}

async function uploadVideoFileChunked(
  file: File,
  onProgress?: (progress: VideoUploadProgress) => void,
): Promise<{ file_id: string; path: string }> {
  const generation = getAuthGeneration()
  const initData = new FormData()
  initData.append('filename', file.name)
  initData.append('size', String(file.size))
  initData.append('content_type', file.type || 'application/octet-stream')

  const initRes = await authFetchWithTimeout(`${API_BASE}/video-notes/upload/init`, {
    method: 'POST',
    body: initData,
  }, 15000)
  if (!initRes.ok) {
    throw new Error(await parseUploadError(initRes, 'Failed to initialize video upload'))
  }

  const init = await initRes.json() as {
    upload_id: string
    chunk_size: number
    total_chunks: number
    recommended_concurrency?: number
  }
  assertSessionGeneration(generation)

  onProgress?.({
    uploadId: init.upload_id,
    phase: 'initializing',
    filename: file.name,
    uploadedBytes: 0,
    assembledBytes: 0,
    totalBytes: file.size,
    uploadedChunks: 0,
    totalChunks: init.total_chunks,
    percent: 0,
    statusText: 'Preparing upload...',
    locationLabel: 'Temporary server upload area',
  })

  let nextIndex = 0
  let completedChunks = 0
  let completedBytes = 0
  let failed = false
  const requestedConcurrency = init.recommended_concurrency ?? DEFAULT_CHUNKED_VIDEO_UPLOAD_CONCURRENCY
  const concurrency = Math.min(
    Math.max(1, requestedConcurrency),
    MAX_CHUNKED_VIDEO_UPLOAD_CONCURRENCY,
    init.total_chunks,
  )
  const uploadChunk = async (index: number) => {
    const start = index * init.chunk_size
    const end = Math.min(file.size, start + init.chunk_size)

    for (let attempt = 0; attempt <= CHUNK_RETRY_ATTEMPTS; attempt++) {
      assertSessionGeneration(generation)
      if (failed) return
      try {
        const chunkBlob = file.slice(start, end)
        const chunkForm = new FormData()
        chunkForm.append('upload_id', init.upload_id)
        chunkForm.append('index', String(index))
        chunkForm.append('chunk', chunkBlob, `${file.name}.part-${index}`)

        const chunkRes = await authFetchWithTimeout(
          `${API_BASE}/video-notes/upload/chunk`,
          { method: 'POST', body: chunkForm },
          CHUNK_UPLOAD_TIMEOUT_MS,
        )
        assertSessionGeneration(generation)
        if (!chunkRes.ok) {
          const canRetry = attempt < CHUNK_RETRY_ATTEMPTS && shouldRetryVideoUploadAsChunked(chunkRes.status)
          if (canRetry) {
            await sleep(CHUNK_RETRY_BASE_MS * 2 ** attempt)
            continue
          }
          throw new Error(await parseUploadError(chunkRes, `Failed to upload chunk ${index + 1}`))
        }

        if (failed) return
        completedChunks += 1
        completedBytes += end - start
        const chunkText = await chunkRes.text()
        assertSessionGeneration(generation)
        let body = {} as { status?: VideoUploadStatus }
        if (chunkText.trim()) {
          try {
            body = JSON.parse(chunkText) as { status?: VideoUploadStatus }
          } catch {
            // Server may return 200 with empty or non-JSON body; progress still advances.
          }
        }
        if (body.status) {
          onProgress?.(toUploadProgress(body.status, file.name))
        } else {
          onProgress?.({
            uploadId: init.upload_id,
            phase: completedChunks >= init.total_chunks ? 'uploaded' : 'uploading',
            filename: file.name,
            uploadedBytes: completedBytes,
            assembledBytes: 0,
            totalBytes: file.size,
            uploadedChunks: completedChunks,
            totalChunks: init.total_chunks,
            percent: Math.min(100, Math.round((completedChunks / init.total_chunks) * 100)),
            statusText: `Uploading to server... ${completedChunks}/${init.total_chunks} chunks sent`,
            locationLabel: 'Temporary server upload area',
          })
        }
        return
      } catch (error) {
        assertSessionGeneration(generation)
        if (isNetworkOrTimeoutError(error) && attempt < CHUNK_RETRY_ATTEMPTS) {
          await sleep(CHUNK_RETRY_BASE_MS * 2 ** attempt)
          continue
        }
        throw error
      }
    }
  }

  const worker = async () => {
    while (true) {
      const current = nextIndex
      nextIndex += 1
      if (failed || current >= init.total_chunks) return
      try { await uploadChunk(current) }
      catch (error) { failed = true; throw error }
    }
  }

  try {
    await Promise.all(Array.from({ length: concurrency }, () => worker()))
  } catch (error) {
    throw error
  }
  assertSessionGeneration(generation)

  onProgress?.({
    uploadId: init.upload_id,
    phase: 'assembling',
    filename: file.name,
    uploadedBytes: file.size,
    assembledBytes: 0,
    totalBytes: file.size,
    uploadedChunks: init.total_chunks,
    totalChunks: init.total_chunks,
    percent: 100,
    statusText: 'Upload complete. Finalizing file on server...',
    locationLabel: 'Temporary server upload area',
  })

  assertSessionGeneration(generation)
  const stopPolling = startAssemblyStatusPolling(init.upload_id, file.name, onProgress)
  try {
    const completeForm = new FormData()
    completeForm.append('upload_id', init.upload_id)
    const completeRes = await authFetchWithTimeout(`${API_BASE}/video-notes/upload/complete`, {
      method: 'POST', body: completeForm,
    }, 120000)
    if (!completeRes.ok) throw new Error(await parseUploadError(completeRes, 'Failed to finalize video upload'))
    const completeBody = await completeRes.json() as {file_id:string;path:string;status?:VideoUploadStatus}
    assertSessionGeneration(generation)
    stopPolling()
    if (completeBody.status) onProgress?.(toUploadProgress(completeBody.status, file.name))
    return completeBody
  } finally { stopPolling() }

}

export async function uploadVideoFile(
  file: File,
  onProgress?: (progress: VideoUploadProgress) => void,
): Promise<{ file_id: string; path: string }> {
  const generation = getAuthGeneration()
  if (file.size > CHUNKED_VIDEO_UPLOAD_THRESHOLD) {
    return uploadVideoFileChunked(file, onProgress)
  }
  const uploadId = `simple-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  onProgress?.({
    uploadId,
    phase: 'uploading',
    filename: file.name,
    uploadedBytes: 0,
    assembledBytes: 0,
    totalBytes: file.size,
    uploadedChunks: 0,
    totalChunks: 1,
    percent: 0,
    statusText: 'Uploading file to server...',
    locationLabel: 'Temporary server upload area',
  })
  let result: { file_id: string; path: string }
  try {
    assertSessionGeneration(generation)
    result = await uploadVideoFileSimple(file)
  } catch (error) {
    assertSessionGeneration(generation)
    if (error instanceof UploadResponseError && shouldRetryVideoUploadAsChunked(error.status)) {
      return uploadVideoFileChunked(file, onProgress)
    }
    if (isNetworkOrTimeoutError(error)) {
      return uploadVideoFileChunked(file, onProgress)
    }
    throw error
  }
  assertSessionGeneration(generation)
  onProgress?.({
    uploadId,
    phase: 'uploaded',
    filename: file.name,
    uploadedBytes: file.size,
    assembledBytes: file.size,
    totalBytes: file.size,
    uploadedChunks: 1,
    totalChunks: 1,
    percent: 100,
    statusText: 'Upload complete. File is saved on the server and ready to process.',
    locationLabel: 'Server upload storage',
  })
  return result
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

export interface DouyinCookieDiagnosis {
  has_cookie: boolean
  looks_usable: boolean
  message: string
  present: string[]
  missing: string[]
  cookie_count: number
  domains: string[]
}

export async function fetchDouyinCookieDiagnosis(): Promise<DouyinCookieDiagnosis> {
  const res = await authFetch(`${API_BASE}/cookies/douyin/diagnose`)
  if (!res.ok) throw new Error('Failed to inspect Douyin cookies')
  return res.json()
}

export async function bilibiliQrGenerate(): Promise<{ qr_url: string; qrcode_key: string }> {
  const res = await authFetch(`${API_BASE}/cookies/bilibili/qr/generate`)
  if (!res.ok) {
    let detail = 'Failed to generate QR code'
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch (e) {
      logIgnoredJsonError('bilibiliQrGenerate', e)
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function bilibiliQrPoll(qrcodeKey: string): Promise<{ status: string; message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/bilibili/qr/poll?qrcode_key=${encodeURIComponent(qrcodeKey)}`)
  if(res.status===404)return {status:'expired',message:'QR session expired. Please generate a new code.'}
  if (!res.ok) {
    let detail = 'Failed to poll QR status'
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch (e) {
      logIgnoredJsonError('bilibiliQrPoll', e)
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function douyinQrGenerate(): Promise<{ qr_url: string; token: string }> {
  const res = await authFetch(`${API_BASE}/cookies/douyin/qr/generate`)
  if (!res.ok) {
    let detail = 'Failed to generate Douyin QR code'
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch (e) {
      logIgnoredJsonError('douyinQrGenerate', e)
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function douyinQrPoll(token: string): Promise<{ status: string; message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/douyin/qr/poll?token=${encodeURIComponent(token)}`)
  if (!res.ok) {
    let detail = 'Failed to poll Douyin QR status'
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch (e) {
      logIgnoredJsonError('douyinQrPoll', e)
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function saveSimpleCookie(platform: string, cookieString: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/cookies/save-simple`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, cookie_string: cookieString }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to save cookie' }))
    throw new Error(err.detail || 'Failed to save cookie')
  }
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

export async function importBrowserCookies(
  platform: string,
  browser: string = 'chrome',
): Promise<{ success: boolean; message: string; cookie_count: number }> {
  const res = await authFetch(`${API_BASE}/cookies/import-browser`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, browser }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Import failed' }))
    throw new Error(err.detail || 'Failed to import browser cookies')
  }
  return res.json()
}

// ==================== Notion ====================

function getNotionKey(): string {
  return getPreference('notion_api_key') || ''
}

export interface NotionPage {
  id: string
  title: string
  icon: string
  url: string
}

export async function fetchNotionPages(query?: string): Promise<{ pages: NotionPage[] }> {
  const params = query ? `?query=${encodeURIComponent(query)}` : ''
  const res = await authFetch(`${API_BASE}/notion/pages${params}`, {
    headers: { 'X-Notion-Key': getNotionKey() },
  })
  return parseApiResponseAsJson(res, 'Failed to fetch Notion pages')
}

export async function exportToNotion(taskId: string, parentPageId: string): Promise<{ url: string; page_id: string; title: string }> {
  const res = await authFetch(`${API_BASE}/notion/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Notion-Key': getNotionKey(),
    },
    body: JSON.stringify({ task_id: taskId, parent_page_id: parentPageId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Export to Notion failed' }))
    throw new Error(err.detail || 'Export to Notion failed')
  }
  return res.json()
}

export async function exportMarkdownToNotion(markdown: string, title: string, parentPageId: string): Promise<{ url: string; page_id: string; title: string }> {
  const res = await authFetch(`${API_BASE}/notion/export-markdown`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Notion-Key': getNotionKey(),
    },
    body: JSON.stringify({ markdown, title, parent_page_id: parentPageId }),
  })
  return parseApiResponseAsJson(res, 'Export to Notion failed')
}

export interface LibraryItem { id:string; kind:'podcast'|'video'; title:string; source:string; date:string; published_at?:string; status:string; thumbnail?:string; platform?:string; duration?:number; topics_count?:number }
export interface LibraryPage { items:LibraryItem[]; next_cursor:string|null }
export function fetchLibrary(filters: string, cursor = '', signal?: AbortSignal): Promise<LibraryPage> {
  const params = new URLSearchParams(filters)
  if (cursor) params.set('cursor', cursor)
  return readJson(`${API_BASE}/library?${params}`, 'Cannot load library', signal)
}

export interface ContentUpdate {
  item_key: string
  kind: 'podcast' | 'video'
  title: string
  source_title: string
  source_id: string
  created_at: string
}
export interface ContentUpdates {items:ContentUpdate[];dismiss_before?:string}
export async function fetchContentUpdates(): Promise<ContentUpdates> {
  const res = await authFetch(`${API_BASE}/content-updates`)
  if (!res.ok) throw new Error('Cannot load new content updates')
  const data = await res.json()
  if (!Array.isArray(data.items)) throw new Error('Invalid content updates response')
  return data
}
export async function dismissContentUpdates(keys: string[], before?:string): Promise<void> {
  const res = await authFetch(`${API_BASE}/content-updates/dismiss`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({keys,before}),
  })
  if (!res.ok) throw new Error('Cannot dismiss new content updates')
}
