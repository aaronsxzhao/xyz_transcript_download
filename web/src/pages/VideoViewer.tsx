import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Copy, Download, Check, FileText, Map, Clock, Loader2,
} from 'lucide-react'
import { fetchVideoTask, type VideoTask } from '../lib/api'
import MarkdownPreview from '../components/video/MarkdownPreview'
import TranscriptPanel from '../components/video/TranscriptPanel'
import MindMapView from '../components/video/MindMapView'

type ViewMode = 'markdown' | 'mindmap' | 'transcript'

export default function VideoViewer() {
  const { taskId } = useParams<{ taskId: string }>()
  const [task, setTask] = useState<VideoTask | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<ViewMode>('markdown')
  const [selectedVersion, setSelectedVersion] = useState<string>('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!taskId) return
    let cancelled = false

    const load = async () => {
      try {
        const data = await fetchVideoTask(taskId)
        if (!cancelled) {
          setTask(data)
          if (data.versions?.length && !selectedVersion) {
            setSelectedVersion(data.versions[0].id)
          }
        }
      } catch (e) {
        console.error('Failed to load task:', e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    // Poll if active
    const interval = setInterval(() => {
      if (task && !['success', 'failed'].includes(task.status)) {
        load()
      }
    }, 3000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [taskId])

  const handleCopy = async () => {
    const content = getCurrentContent()
    if (!content) return
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const content = getCurrentContent()
    if (!content || !task) return
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${task.title || 'notes'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const getCurrentContent = (): string => {
    if (!task) return ''
    if (selectedVersion && task.versions) {
      const ver = task.versions.find(v => v.id === selectedVersion)
      if (ver) return ver.content
    }
    return task.markdown || ''
  }

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-screen text-gray-500">
        <p>Task not found</p>
        <Link to="/videos" className="text-indigo-400 mt-2">Back to Videos</Link>
      </div>
    )
  }

  const versions = task.versions || []

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/videos"
            className="p-1.5 text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={20} />
          </Link>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-white truncate">
              {task.title || 'Untitled'}
            </h1>
            <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
              {task.style && (
                <span className="px-2 py-0.5 bg-purple-600/20 text-purple-400 rounded-full">
                  {task.style}
                </span>
              )}
              {task.duration > 0 && (
                <span className="flex items-center gap-1">
                  <Clock size={11} /> {formatDuration(task.duration)}
                </span>
              )}
              {task.platform && (
                <span className="text-gray-500">{task.platform}</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Version selector */}
          {versions.length > 1 && (
            <select
              value={selectedVersion}
              onChange={e => setSelectedVersion(e.target.value)}
              className="px-2 py-1 bg-dark-hover border border-dark-border rounded text-sm text-white"
            >
              {versions.map((v, i) => (
                <option key={v.id} value={v.id}>
                  v{versions.length - i} - {v.style || 'default'}
                </option>
              ))}
            </select>
          )}

          {/* View mode tabs */}
          <div className="flex bg-dark-hover rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('markdown')}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                viewMode === 'markdown'
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <FileText size={14} className="inline mr-1" />
              Note
            </button>
            <button
              onClick={() => setViewMode('mindmap')}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                viewMode === 'mindmap'
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Map size={14} className="inline mr-1" />
              Mind Map
            </button>
            <button
              onClick={() => setViewMode('transcript')}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                viewMode === 'transcript'
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Transcript
            </button>
          </div>

          {/* Actions */}
          <button
            onClick={handleCopy}
            className="p-2 text-gray-400 hover:text-white transition-colors"
            title="Copy"
          >
            {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
          </button>
          <button
            onClick={handleDownload}
            className="p-2 text-gray-400 hover:text-white transition-colors"
            title="Download .md"
          >
            <Download size={16} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden bg-dark-surface rounded-xl border border-dark-border p-4">
        {viewMode === 'markdown' && (
          <MarkdownPreview task={{
            ...task,
            markdown: getCurrentContent(),
          }} />
        )}
        {viewMode === 'mindmap' && (
          <MindMapView markdown={getCurrentContent()} />
        )}
        {viewMode === 'transcript' && (
          <TranscriptPanel transcript={task.transcript} />
        )}
      </div>
    </div>
  )
}
