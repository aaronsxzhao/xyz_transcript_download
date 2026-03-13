import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play, Loader2, Settings2, ChevronDown, ChevronUp, AlertTriangle, Upload,
} from 'lucide-react'
import { generateVideoNote, uploadVideoFile, getUserModelSettings, validateBilibiliCookie, fetchCookieStatus, getVideoProcessingDefaults } from '../../lib/api'
import YouTubeCookieGuide from './YouTubeCookieGuide'
import PlatformIcon, { PLATFORM_COLORS } from '../PlatformIcon'
import { useStore } from '../../lib/store'

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: 'Bilibili',
  youtube: 'YouTube',
  douyin: 'Douyin',
  kuaishou: 'Kuaishou',
  local: 'Local File',
}

function detectPlatform(url: string): string {
  const u = url.toLowerCase()
  if (/bilibili\.com|b23\.tv/.test(u)) return 'bilibili'
  if (/youtube\.com|youtu\.be/.test(u)) return 'youtube'
  if (/douyin\.com|tiktok\.com/.test(u)) return 'douyin'
  if (/kuaishou\.com|kwai\.com/.test(u)) return 'kuaishou'
  return ''
}

const STYLES = [
  { id: 'minimal', label: '精简 Minimal' },
  { id: 'detailed', label: '详细 Detailed' },
  { id: 'academic', label: '学术 Academic' },
  { id: 'tutorial', label: '教程 Tutorial' },
  { id: 'xiaohongshu', label: '小红书 Social' },
  { id: 'life_journal', label: '生活向 Journal' },
  { id: 'task_oriented', label: '任务导向 Tasks' },
  { id: 'business', label: '商业 Business' },
  { id: 'meeting_minutes', label: '会议纪要 Minutes' },
]

const FORMATS = [
  { id: 'toc', label: 'Table of Contents' },
  { id: 'link', label: 'Timestamp Links' },
  { id: 'screenshot', label: 'Screenshots' },
  { id: 'summary', label: 'AI Summary' },
]

const AUDIO_QUALITIES = [
  { id: 'fast', label: 'Fast', sub: '32k' },
  { id: 'medium', label: 'Medium', sub: '64k' },
  { id: 'slow', label: 'High', sub: '128k' },
]

const VIDEO_QUALITIES = [
  { id: '360', label: '360p' },
  { id: '480', label: '480p' },
  { id: '720', label: '720p' },
  { id: '1080', label: '1080p' },
  { id: 'best', label: 'Best' },
]

interface Props {
  onTaskCreated?: (task: { taskId: string; title: string; url: string; platform: string }) => void
  hideTitle?: boolean
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value >= 100 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

export default function VideoNoteForm({ onTaskCreated, hideTitle }: Props) {
  const navigate = useNavigate()
  const savedDefaults = useMemo(() => getVideoProcessingDefaults(), [])
  const { uploadSessions, upsertUploadSession, removeUploadSession } = useStore()
  const [url, setUrl] = useState('')
  const [isLocalFile, setIsLocalFile] = useState(false)
  const [style, setStyle] = useState(() => (savedDefaults.style as string) || 'detailed')
  const [formats, setFormats] = useState<string[]>(() => {
    const value = savedDefaults.formats
    return Array.isArray(value) ? value as string[] : ['toc', 'summary', 'screenshot']
  })
  const [quality, setQuality] = useState(() => (savedDefaults.quality as string) || 'medium')
  const [videoQuality, setVideoQuality] = useState(() => (savedDefaults.video_quality as string) || '720')
  const [extras, setExtras] = useState('')
  const [videoUnderstanding, setVideoUnderstanding] = useState(false)
  const [videoInterval, setVideoInterval] = useState(4)
  const [gridCols, setGridCols] = useState(3)
  const [gridRows, setGridRows] = useState(3)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeUploadId, setActiveUploadId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeUpload = uploadSessions.find(s => s.id === activeUploadId) || null

  const detectedPlatform = useMemo(() => isLocalFile ? 'local' : detectPlatform(url), [url, isLocalFile])

  const [ytCookieWarning, setYtCookieWarning] = useState(false)
  const ytCheckRef = useRef(false)

  useEffect(() => {
    if (detectedPlatform === 'youtube' && !ytCheckRef.current) {
      ytCheckRef.current = true
      fetchCookieStatus('youtube')
        .then(r => setYtCookieWarning(!r.has_cookie))
        .catch(() => setYtCookieWarning(false))
    } else if (detectedPlatform !== 'youtube') {
      ytCheckRef.current = false
      setYtCookieWarning(false)
    }
  }, [detectedPlatform])

  useEffect(() => {
    if (activeUpload?.path) {
      setUrl(prev => prev || activeUpload.path || '')
      setIsLocalFile(true)
    }
  }, [activeUpload?.path])

  const toggleFormat = (id: string) => {
    setFormats(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  const handleFileUpload = async (file: File) => {
    setError('')
    setIsLocalFile(true)
    const fallbackUploadId = `pending-${Date.now()}`
    let sessionId = fallbackUploadId
    setActiveUploadId(fallbackUploadId)
    upsertUploadSession({
      id: fallbackUploadId,
      uploadId: fallbackUploadId,
      phase: 'initializing',
      filename: file.name,
      uploadedBytes: 0,
      assembledBytes: 0,
      totalBytes: file.size,
      uploadedChunks: 0,
      totalChunks: 0,
      percent: 0,
      statusText: 'Preparing upload...',
      locationLabel: 'Temporary server upload area',
    })
    try {
      const result = await uploadVideoFile(file, progress => {
        if (progress.uploadId !== sessionId) {
          removeUploadSession(sessionId)
          sessionId = progress.uploadId
          setActiveUploadId(sessionId)
        }
        upsertUploadSession({
          id: progress.uploadId,
          ...progress,
        })
      })
      setUrl(result.path)
      upsertUploadSession({
        id: sessionId,
        uploadId: sessionId,
        phase: 'uploaded',
        filename: file.name,
        uploadedBytes: file.size,
        assembledBytes: file.size,
        totalBytes: file.size,
        uploadedChunks: activeUpload?.uploadedChunks || 1,
        totalChunks: activeUpload?.totalChunks || 1,
        percent: 100,
        statusText: 'Upload complete. File is saved on the server and ready to process.',
        locationLabel: 'Server upload storage',
        path: result.path,
      })
    } catch (e: any) {
      upsertUploadSession({
        id: sessionId,
        uploadId: sessionId,
        phase: 'failed',
        filename: file.name,
        uploadedBytes: 0,
        assembledBytes: 0,
        totalBytes: file.size,
        uploadedChunks: 0,
        totalChunks: 0,
        percent: 0,
        statusText: 'Upload failed',
        locationLabel: 'Temporary server upload area',
        error: e?.message || 'Failed to upload local video',
      })
      setError(
        e?.message ||
        'Failed to upload local video. If you are on the hosted site, very large files may need chunked upload.'
      )
    }
  }

  const submittingRef = useRef(false)

  const handleSubmit = async () => {
    if (!url.trim() || submittingRef.current) return
    submittingRef.current = true
    setLoading(true)
    setError('')

    try {
      if (detectedPlatform === 'bilibili') {
        try {
          const cookieCheck = await validateBilibiliCookie()
          if (!cookieCheck.valid) {
            setError('BiliBili login required. Please go to Settings → Platform Accounts → BiliBili to log in first.')
            return
          }
        } catch {
          setError('Could not verify BiliBili login status. Please check Settings → Platform Accounts.')
          return
        }
      }

      const modelSettings = getUserModelSettings()
      if (isLocalFile && activeUpload) {
        upsertUploadSession({
          ...activeUpload,
          id: activeUpload.id,
          phase: 'queueing',
          percent: 100,
          statusText: 'Upload complete. Creating note task...',
          locationLabel: 'Server upload storage',
        })
      }
      const result = await generateVideoNote({
        url: url.trim(),
        title: detectedPlatform === 'local' ? (activeUpload?.filename?.replace(/\.[^.]+$/, '') || 'Local video') : undefined,
        platform: detectedPlatform,
        style,
        formats,
        quality,
        video_quality: videoQuality,
        llm_model: modelSettings.llm_model,
        extras,
        video_understanding: videoUnderstanding,
        video_interval: videoInterval,
        grid_cols: gridCols,
        grid_rows: gridRows,
      })
      const localTitle = activeUpload?.filename?.replace(/\.[^.]+$/, '') || 'Local video'
      onTaskCreated?.({
        taskId: result.task_id,
        title: detectedPlatform === 'local' ? localTitle : '',
        url: url.trim(),
        platform: detectedPlatform,
      })
      if (activeUpload) removeUploadSession(activeUpload.id)
      setUrl('')
      setIsLocalFile(false)
      setActiveUploadId(null)
    } catch (e: any) {
      const msg = e?.message || 'Unknown error'
      console.error('Failed to generate note:', msg)
      if (isLocalFile && activeUpload) {
        upsertUploadSession({
          ...activeUpload,
          id: activeUpload.id,
          phase: 'uploaded',
          statusText: 'Upload complete. Ready to create note task.',
          locationLabel: 'Server upload storage',
        })
      }
      setError(msg)
    } finally {
      setLoading(false)
      submittingRef.current = false
    }
  }

  return (
    <div className="space-y-3">
      {!hideTitle && <h3 className="text-base font-semibold text-white">Generate Video Notes</h3>}

      {/* URL input + auto-detected platform badge + local upload */}
      <div>
        <div className="flex gap-1.5">
          {isLocalFile ? (
            <div className="flex-1 px-3 py-2.5 bg-dark-hover border border-dark-border rounded-lg">
              <div className="flex items-start gap-2">
                <PlatformIcon platform="local" size={14} className={PLATFORM_COLORS['local'] || 'text-gray-400'} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-white truncate">{activeUpload?.filename || 'Local file'}</span>
                    <span className="text-[11px] text-gray-500 whitespace-nowrap">{activeUpload?.percent ?? 0}%</span>
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    {activeUpload?.statusText || 'Choose a local file to upload'}
                  </div>
                  <div className="mt-1 h-1.5 bg-dark-border rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        activeUpload?.phase === 'failed' ? 'bg-red-500' : 'bg-indigo-500'
                      }`}
                      style={{ width: `${Math.max(4, activeUpload?.percent ?? 0)}%` }}
                    />
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-500">
                    <span>
                      {formatBytes(activeUpload?.uploadedBytes || 0)} / {formatBytes(activeUpload?.totalBytes || 0)}
                    </span>
                    {(activeUpload?.totalChunks || 0) > 0 && (
                      <span>{activeUpload?.uploadedChunks || 0}/{activeUpload?.totalChunks || 0} chunks</span>
                    )}
                    <span>{activeUpload?.locationLabel || 'Temporary server upload area'}</span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setUrl('')
                    setIsLocalFile(false)
                    if (activeUpload) removeUploadSession(activeUpload.id)
                    setActiveUploadId(null)
                  }}
                  className="text-xs text-gray-500 hover:text-red-400 transition-colors"
                >
                  Clear
                </button>
              </div>
            </div>
          ) : (
            <div className="flex-1 relative">
              <input
                type="text"
                value={url}
                onChange={e => {
                  setUrl(e.target.value)
                  setIsLocalFile(false)
                  if (activeUpload) removeUploadSession(activeUpload.id)
                  setActiveUploadId(null)
                }}
                placeholder="Paste video URL here..."
                className="w-full px-3 py-2.5 bg-dark-hover border border-dark-border rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 pr-24"
              />
              {detectedPlatform && (
                <span className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-600/20 border border-indigo-500/30 text-[11px] text-indigo-400">
                  <PlatformIcon platform={detectedPlatform} size={12} className="text-indigo-400" />
                  {PLATFORM_LABELS[detectedPlatform] || detectedPlatform}
                </span>
              )}
            </div>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3 py-2.5 bg-dark-hover border border-dark-border rounded-lg text-gray-400 hover:text-white transition-colors flex items-center gap-1.5 text-xs whitespace-nowrap"
            title="Upload local video file"
          >
            <Upload size={14} />
            <span className="hidden sm:inline">Local File</span>
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
            accept="video/*,.mp4,.mkv,.avi,.mov,.webm,.flv,.wmv,.m4v"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) handleFileUpload(file)
            e.currentTarget.value = ''
          }}
        />
      </div>

      {/* YouTube cookie warning */}
      {ytCookieWarning && detectedPlatform === 'youtube' && (
        <div className="flex items-start gap-2 p-2.5 bg-amber-900/20 border border-amber-500/30 rounded-lg">
          <AlertTriangle size={14} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-300/90">
            <p className="font-medium">YouTube cookies not set</p>
            <p className="mt-0.5 text-amber-300/70">
              YouTube may block requests from cloud servers. Upload cookies in{' '}
              <button
                onClick={() => navigate('/settings')}
                className="text-indigo-400 hover:text-indigo-300 underline"
              >
                Settings → Platform Accounts
              </button>{' '}
              to avoid failures.
            </p>
          </div>
        </div>
      )}

      {/* Note Style */}
      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Note Style</label>
        <select
          value={style}
          onChange={e => setStyle(e.target.value)}
          className="w-full px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500"
        >
          {STYLES.map(s => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Include Formats */}
      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Include</label>
        <div className="flex flex-wrap gap-1.5">
          {FORMATS.map(f => (
            <label
              key={f.id}
              className={`px-3 py-1.5 rounded-lg text-xs cursor-pointer transition-colors whitespace-nowrap ${
                formats.includes(f.id)
                  ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                  : 'bg-dark-hover text-gray-400 border border-transparent hover:text-white'
              }`}
            >
              <input
                type="checkbox"
                checked={formats.includes(f.id)}
                onChange={() => toggleFormat(f.id)}
                className="hidden"
              />
              {f.label}
            </label>
          ))}
        </div>
      </div>

      {/* Audio Quality */}
      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Audio Quality</label>
        <div className="flex gap-1.5">
          {AUDIO_QUALITIES.map(q => (
            <button
              key={q.id}
              onClick={() => setQuality(q.id)}
              className={`flex-1 flex flex-col items-center py-2 rounded-lg text-xs transition-colors ${
                quality === q.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-dark-hover text-gray-400 hover:text-white'
              }`}
            >
              <span className="font-medium">{q.label}</span>
              <span className={`text-[10px] mt-0.5 ${quality === q.id ? 'text-indigo-200' : 'text-gray-500'}`}>{q.sub}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Video Quality */}
      <div>
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Video Quality</label>
        <div className="flex gap-1.5">
          {VIDEO_QUALITIES.map(q => (
            <button
              key={q.id}
              onClick={() => setVideoQuality(q.id)}
              className={`flex-1 py-2 rounded-lg text-xs text-center transition-colors ${
                videoQuality === q.id
                  ? 'bg-indigo-600 text-white font-medium'
                  : 'bg-dark-hover text-gray-400 hover:text-white'
              }`}
            >
              {q.label}
            </button>
          ))}
        </div>
      </div>

      {/* Advanced Options */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-white transition-colors"
      >
        <Settings2 size={12} />
        Advanced Options
        {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showAdvanced && (
        <div className="p-3 bg-dark-hover/50 border border-dark-border rounded-lg space-y-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={videoUnderstanding}
              onChange={e => setVideoUnderstanding(e.target.checked)}
              className="rounded bg-dark-hover border-dark-border text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-xs text-gray-300">Multimodal Video Understanding</span>
          </label>

          {videoUnderstanding && (
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Interval (s)</label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={videoInterval}
                  onChange={e => setVideoInterval(parseInt(e.target.value) || 4)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-xs text-white"
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Grid Cols</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={gridCols}
                  onChange={e => setGridCols(parseInt(e.target.value) || 3)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-xs text-white"
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-500 mb-1">Grid Rows</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={gridRows}
                  onChange={e => setGridRows(parseInt(e.target.value) || 3)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-xs text-white"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Extra Instructions</label>
            <textarea
              value={extras}
              onChange={e => setExtras(e.target.value)}
              placeholder="Additional instructions for the AI..."
              rows={2}
              className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="p-3 bg-red-900/30 border border-red-500/50 rounded-lg text-xs text-red-300">
          <p>{error}</p>
          {error.toLowerCase().includes('login') && detectedPlatform === 'youtube' && (
            <div className="mt-3 p-3 bg-dark-hover rounded-lg border border-dark-border">
              <YouTubeCookieGuide compact />
            </div>
          )}
          {error.includes('Settings') && (
            <button
              onClick={() => navigate('/settings')}
              className="mt-1.5 text-indigo-400 hover:text-indigo-300 underline text-xs"
            >
              Open Settings
            </button>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={loading || !url.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg font-medium text-sm transition-colors"
      >
        {loading ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <Play size={16} />
            Generate Notes
          </>
        )}
      </button>
    </div>
  )
}
