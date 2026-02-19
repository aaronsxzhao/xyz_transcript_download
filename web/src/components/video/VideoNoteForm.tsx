import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play, Loader2, Settings2, ChevronDown, ChevronUp,
} from 'lucide-react'
import { generateVideoNote, uploadVideoFile, getUserModelSettings, validateBilibiliCookie } from '../../lib/api'

const PLATFORMS = [
  { id: 'bilibili', label: 'Bilibili', icon: '📺' },
  { id: 'youtube', label: 'YouTube', icon: '▶️' },
  { id: 'douyin', label: 'Douyin', icon: '🎵' },
  { id: 'kuaishou', label: 'Kuaishou', icon: '⚡' },
  { id: 'local', label: 'Local File', icon: '📁' },
]

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
  { id: 'fast', label: 'Fast', sub: '32kbps' },
  { id: 'medium', label: 'Medium', sub: '64kbps' },
  { id: 'slow', label: 'High', sub: '128kbps' },
]

const VIDEO_QUALITIES = [
  { id: '360', label: '360p' },
  { id: '480', label: '480p' },
  { id: '720', label: '720p' },
  { id: '1080', label: '1080p' },
  { id: 'best', label: 'Best' },
]

interface Props {
  onTaskCreated?: (taskId: string) => void
}

function isBilibiliUrl(url: string): boolean {
  return /bilibili\.com|b23\.tv/i.test(url)
}

export default function VideoNoteForm({ onTaskCreated }: Props) {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [platform, setPlatform] = useState('')
  const [style, setStyle] = useState('detailed')
  const [formats, setFormats] = useState<string[]>(['toc', 'summary'])
  const [quality, setQuality] = useState('medium')
  const [videoQuality, setVideoQuality] = useState('720')
  const [extras, setExtras] = useState('')
  const [videoUnderstanding, setVideoUnderstanding] = useState(false)
  const [videoInterval, setVideoInterval] = useState(4)
  const [gridCols, setGridCols] = useState(3)
  const [gridRows, setGridRows] = useState(3)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [uploadProgress, setUploadProgress] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const toggleFormat = (id: string) => {
    setFormats(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  const handleFileUpload = async (file: File) => {
    setUploadProgress('Uploading...')
    try {
      const result = await uploadVideoFile(file)
      setUrl(result.path)
      setPlatform('local')
      setUploadProgress(`Uploaded: ${file.name}`)
    } catch (e) {
      setUploadProgress('Upload failed')
    }
  }

  const handleSubmit = async () => {
    if (!url.trim()) return
    setLoading(true)
    setError('')

    if (isBilibiliUrl(url.trim())) {
      try {
        const cookieCheck = await validateBilibiliCookie()
        if (!cookieCheck.valid) {
          setError('BiliBili login required. Please go to Settings → BiliBili Login to scan the QR code first.')
          setLoading(false)
          return
        }
      } catch {
        setError('Could not verify BiliBili login status. Please check Settings → BiliBili Login.')
        setLoading(false)
        return
      }
    }

    try {
      const modelSettings = getUserModelSettings()
      const result = await generateVideoNote({
        url: url.trim(),
        platform,
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
        max_output_tokens: modelSettings.max_output_tokens,
      })
      onTaskCreated?.(result.task_id)
      setUrl('')
      setUploadProgress('')
    } catch (e: any) {
      const msg = e?.message || 'Unknown error'
      console.error('Failed to generate note:', msg)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold text-white">Generate Video Notes</h3>

      {/* URL & Platform Card */}
      <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-3">
        <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider">Platform</label>
        <div className="flex flex-wrap gap-1.5">
          {PLATFORMS.map(p => (
            <button
              key={p.id}
              onClick={() => {
                setPlatform(p.id)
                if (p.id === 'local') fileInputRef.current?.click()
              }}
              className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                platform === p.id
                  ? 'bg-indigo-600 text-white'
                  : 'bg-dark-hover text-gray-400 hover:text-white'
              }`}
            >
              {p.icon} {p.label}
            </button>
          ))}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) handleFileUpload(file)
          }}
        />
        {uploadProgress && (
          <p className="text-xs text-gray-500">{uploadProgress}</p>
        )}

        {platform !== 'local' && (
          <input
            type="text"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="Paste video URL here..."
            className="w-full px-3 py-2.5 bg-dark-hover border border-dark-border rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />
        )}
      </div>

      {/* Style & Format Card */}
      <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Note Style</label>
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

        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Include</label>
          <div className="grid grid-cols-2 gap-1.5">
            {FORMATS.map(f => (
              <label
                key={f.id}
                className={`flex items-center justify-center px-2 py-1.5 rounded-lg text-xs cursor-pointer transition-colors ${
                  formats.includes(f.id)
                    ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/50'
                    : 'bg-dark-hover text-gray-400 border border-transparent'
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
      </div>

      {/* Quality Card */}
      <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Audio Quality</label>
          <div className="grid grid-cols-3 gap-1.5">
            {AUDIO_QUALITIES.map(q => (
              <label
                key={q.id}
                className={`flex flex-col items-center py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                  quality === q.id
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-hover text-gray-400 hover:text-white'
                }`}
              >
                <input
                  type="radio"
                  name="quality"
                  value={q.id}
                  checked={quality === q.id}
                  onChange={() => setQuality(q.id)}
                  className="hidden"
                />
                <span className="font-medium">{q.label}</span>
                <span className={`text-[10px] ${quality === q.id ? 'text-indigo-200' : 'text-gray-500'}`}>{q.sub}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Video Quality</label>
          <div className="grid grid-cols-5 gap-1.5">
            {VIDEO_QUALITIES.map(q => (
              <label
                key={q.id}
                className={`flex items-center justify-center py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                  videoQuality === q.id
                    ? 'bg-indigo-600 text-white font-medium'
                    : 'bg-dark-hover text-gray-400 hover:text-white'
                }`}
              >
                <input
                  type="radio"
                  name="videoQuality"
                  value={q.id}
                  checked={videoQuality === q.id}
                  onChange={() => setVideoQuality(q.id)}
                  className="hidden"
                />
                {q.label}
              </label>
            ))}
          </div>
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
        <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={videoUnderstanding}
              onChange={e => setVideoUnderstanding(e.target.checked)}
              className="rounded bg-dark-hover border-dark-border text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-gray-300">Multimodal Video Understanding</span>
          </label>

          {videoUnderstanding && (
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Interval (s)</label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={videoInterval}
                  onChange={e => setVideoInterval(parseInt(e.target.value) || 4)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-sm text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Grid Cols</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={gridCols}
                  onChange={e => setGridCols(parseInt(e.target.value) || 3)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-sm text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Grid Rows</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={gridRows}
                  onChange={e => setGridRows(parseInt(e.target.value) || 3)}
                  className="w-full px-2 py-1.5 bg-dark-hover border border-dark-border rounded-lg text-sm text-white"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-500 mb-1">Extra Instructions</label>
            <textarea
              value={extras}
              onChange={e => setExtras(e.target.value)}
              placeholder="Additional instructions for the AI..."
              rows={2}
              className="w-full px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="p-3 bg-red-900/30 border border-red-500/50 rounded-xl text-sm text-red-300">
          <p>{error}</p>
          {error.includes('Settings') && (
            <button
              onClick={() => navigate('/settings')}
              className="mt-2 text-indigo-400 hover:text-indigo-300 underline text-xs"
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
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-xl font-medium transition-colors"
      >
        {loading ? (
          <>
            <Loader2 size={18} className="animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <Play size={18} />
            Generate Notes
          </>
        )}
      </button>
    </div>
  )
}
