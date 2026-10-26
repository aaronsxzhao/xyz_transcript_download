import type {LocalAudioUploadResult} from './api'
import {authFetch,assertSessionGeneration,logIgnoredJsonError} from './api'
import {getAuthGeneration} from './auth'
const API_BASE='/api'
const CHUNKED_AUDIO_UPLOAD_THRESHOLD = 8 * 1024 * 1024

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
