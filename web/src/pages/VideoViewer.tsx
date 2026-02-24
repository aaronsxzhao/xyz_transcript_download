import { useEffect, useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Copy, Download, Check, FileText, Map, Clock, Loader2,
  ChevronRight, FileDown, RefreshCw, XCircle, ExternalLink, RotateCcw,
} from 'lucide-react'
import { fetchVideoTask, retryVideoTask, type VideoTask } from '../lib/api'
import MarkdownPreview from '../components/video/MarkdownPreview'
import TranscriptPanel from '../components/video/TranscriptPanel'
import MindMapView from '../components/video/MindMapView'

type ViewMode = 'markdown' | 'mindmap' | 'transcript'

interface TocItem {
  level: number
  text: string
  slug: string
}

function extractToc(markdown: string): TocItem[] {
  const items: TocItem[] = []
  const slugCounts: Record<string, number> = {}
  for (const match of markdown.matchAll(/^(#{1,3})\s+(.+)$/gm)) {
    const level = match[1].length
    const text = match[2].trim()
    let slug = text.toLowerCase()
      .replace(/[^\w\u4e00-\u9fff\s-]/g, '')
      .trim().replace(/\s+/g, '-')
      .replace(/-+/g, '-')
    const base = slug
    const n = slugCounts[base] || 0
    if (n > 0) slug = `${base}-${n}`
    slugCounts[base] = n + 1
    items.push({ level, text, slug })
  }
  return items
}

export default function VideoViewer() {
  const { taskId } = useParams<{ taskId: string }>()
  const [task, setTask] = useState<VideoTask | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<ViewMode>('markdown')
  const [selectedVersion, setSelectedVersion] = useState<string>('')
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

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
    const md = getCurrentContent()
    if (!md || !task) return
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${task.title || 'notes'}.md`
    document.body.appendChild(a)
    a.click()
    setTimeout(() => {
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }, 100)
  }

  const handleDownloadPdf = async () => {
    const md = getCurrentContent()
    if (!md || pdfLoading) return
    setPdfLoading(true)
    try {
      const markedModule = await import('marked')
      const { marked } = markedModule
      marked.setOptions({ gfm: true, breaks: false })
      const body = await marked.parse(md)

      // Open a new window for printing — works reliably across browsers
      const printWin = window.open('', '_blank', 'width=800,height=600')
      if (!printWin) {
        alert('Please allow popups to download PDF')
        return
      }
      printWin.document.write(`<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>${task?.title || 'Notes'}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; background: #fff; padding: 20px 30px; font-size: 13px; line-height: 1.75; }
  h1 { font-size: 22px; font-weight: 700; color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; margin: 24px 0 16px; }
  h2 { font-size: 18px; font-weight: 700; color: #1e40af; margin: 28px 0 12px; }
  h3 { font-size: 15px; font-weight: 600; color: #1f2937; margin: 20px 0 8px; }
  h4, h5, h6 { font-size: 14px; font-weight: 600; color: #374151; margin: 16px 0 6px; }
  p { font-size: 13px; line-height: 1.75; color: #374151; margin: 8px 0; }
  li { font-size: 13px; line-height: 1.75; color: #374151; }
  ul, ol { padding-left: 20px; margin: 6px 0; }
  strong { color: #111827; }
  a { color: #4f46e5; text-decoration: none; }
  blockquote { border-left: 3px solid #6366f1; background: #eef2ff; color: #374151; padding: 10px 16px; margin: 12px 0; border-radius: 0 6px 6px 0; font-size: 13px; }
  blockquote p { margin: 4px 0; }
  code { font-family: "SF Mono", "Fira Code", monospace; font-size: 12px; color: #6366f1; background: #f3f4f6; padding: 1px 5px; border-radius: 3px; }
  pre { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; overflow-x: auto; margin: 12px 0; }
  pre code { background: none; padding: 0; color: #1f2937; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12.5px; }
  th { background: #f3f4f6; font-weight: 600; color: #111827; text-align: left; padding: 8px 10px; border: 1px solid #d1d5db; }
  td { padding: 8px 10px; border: 1px solid #d1d5db; color: #374151; }
  hr { border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }
  img { max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #e5e7eb; margin: 10px 0; }
  @media print {
    body { padding: 0; }
    table, img, blockquote, pre { page-break-inside: avoid; }
    h1, h2, h3 { page-break-after: avoid; }
  }
</style>
</head><body>${body}</body></html>`)
      printWin.document.close()
      // Wait for content to render then trigger print (Save as PDF)
      printWin.onload = () => {
        setTimeout(() => {
          printWin.print()
          printWin.close()
        }, 500)
      }
      // Fallback if onload already fired
      setTimeout(() => {
        if (!printWin.closed) {
          printWin.print()
          printWin.close()
        }
      }, 2000)
    } catch (e) {
      console.error('PDF generation failed:', e)
    } finally {
      setPdfLoading(false)
    }
  }

  const handleRegenerate = async () => {
    if (!task || regenerating) return
    setRegenerating(true)
    try {
      await retryVideoTask(task.id)
    } catch (e) {
      console.error('Regenerate failed:', e)
    } finally {
      setRegenerating(false)
    }
  }

  const getCurrentContent = (): string => {
    if (!task) return ''
    if (selectedVersion && task.versions?.length) {
      const ver = task.versions.find(v => v.id === selectedVersion)
      if (ver?.content) return ver.content
    }
    return task.markdown || ''
  }

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const content = getCurrentContent()
  const toc = useMemo(() => extractToc(content), [content])

  const scrollToHeading = (slug: string) => {
    const el = document.getElementById(slug)
    if (!el) return
    const container = document.getElementById('video-content-scroll')
    if (container) {
      const elRect = el.getBoundingClientRect()
      const containerRect = container.getBoundingClientRect()
      const scrollTop = container.scrollTop + (elRect.top - containerRect.top) - 12
      container.scrollTo({ top: Math.max(0, scrollTop), behavior: 'smooth' })
    } else {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-gray-500">
        <p>Task not found</p>
        <Link to="/videos" className="text-indigo-400 mt-2">Back to Videos</Link>
      </div>
    )
  }

  const versions = task.versions || []

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] md:h-[calc(100vh-6rem)]">
      {/* Fixed header bar */}
      <div className="flex items-center justify-between pb-3 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to="/videos"
            className="p-1.5 text-gray-400 hover:text-white transition-colors flex-shrink-0"
          >
            <ArrowLeft size={18} />
          </Link>
          <div className="min-w-0">
            <h1 className="text-base font-semibold text-white truncate">
              {task.title || (task.url ? (() => {
                try {
                  const u = new URL(task.url)
                  return u.hostname.replace('www.', '') + u.pathname.replace(/\/$/, '')
                } catch { return task.url }
              })() : 'Untitled')}
            </h1>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
              {task.status === 'failed' && (
                <span className="px-1.5 py-0.5 bg-red-600/20 text-red-400 rounded-full text-[10px]">
                  Failed
                </span>
              )}
              {task.style && (
                <span className="px-1.5 py-0.5 bg-purple-600/20 text-purple-400 rounded-full text-[10px]">
                  {task.style}
                </span>
              )}
              {task.duration > 0 && (
                <span className="flex items-center gap-1">
                  <Clock size={10} /> {formatDuration(task.duration)}
                </span>
              )}
              {task.platform && <span>{task.platform}</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {versions.length > 1 && (
            <select
              value={selectedVersion}
              onChange={e => setSelectedVersion(e.target.value)}
              className="px-2 py-1 bg-dark-hover border border-dark-border rounded text-xs text-white"
            >
              {versions.map((v, i) => (
                <option key={v.id} value={v.id}>
                  v{versions.length - i} - {v.style || 'default'}
                </option>
              ))}
            </select>
          )}

          <div className="flex bg-dark-hover rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('markdown')}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                viewMode === 'markdown' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <FileText size={12} className="inline mr-1" />
              Note
            </button>
            <button
              onClick={() => setViewMode('mindmap')}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                viewMode === 'mindmap' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              <Map size={12} className="inline mr-1" />
              Mind Map
            </button>
            <button
              onClick={() => setViewMode('transcript')}
              className={`px-2.5 py-1 rounded text-xs transition-colors ${
                viewMode === 'transcript' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              Transcript
            </button>
          </div>

          {content && (
            <>
              <button
                onClick={handleCopy}
                className="p-1.5 text-gray-400 hover:text-white transition-colors"
                title="Copy"
              >
                {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
              </button>
              <button
                onClick={handleDownload}
                className="p-1.5 text-gray-400 hover:text-white transition-colors"
                title="Download .md"
              >
                <Download size={14} />
              </button>
              {task.status === 'success' && (
                <button
                  onClick={handleDownloadPdf}
                  disabled={pdfLoading}
                  className="p-1.5 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                  title="Download PDF"
                >
                  {pdfLoading ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
                </button>
              )}
            </>
          )}
          {(['success', 'failed', 'cancelled'].includes(task.status)) && (
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className="flex items-center gap-1 ml-1 px-2 py-1 text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 hover:border-indigo-400/50 rounded-lg transition-colors disabled:opacity-50"
              title="Regenerate notes"
            >
              <RefreshCw size={13} className={regenerating ? 'animate-spin' : ''} />
              Regenerate
            </button>
          )}
        </div>
      </div>

      {/* Failed state banner */}
      {task.status === 'failed' && (
        <div className="flex-shrink-0 mb-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-red-400 mb-1">Processing Failed</h3>
              {(task.error || task.message) && (
                <p className="text-xs text-red-400/80 mb-2">{task.error || task.message}</p>
              )}
              {task.url && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 mb-2"
                >
                  <ExternalLink size={10} />
                  <span className="truncate max-w-xs">{task.url}</span>
                </a>
              )}
              <div className="flex items-center gap-2 mt-1">
                <button
                  onClick={handleRegenerate}
                  disabled={regenerating}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
                >
                  <RotateCcw size={12} className={regenerating ? 'animate-spin' : ''} />
                  Retry
                </button>
                <Link
                  to="/settings"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-hover hover:bg-dark-border text-gray-300 text-xs rounded-lg transition-colors"
                >
                  Check Settings
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Two-column layout: both columns scroll independently within viewport */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Left sidebar: scrolls independently */}
        <aside className="w-64 flex-shrink-0 hidden lg:flex flex-col gap-3 overflow-y-auto custom-scrollbar">
          {/* Metadata card */}
          <div className="bg-dark-surface rounded-xl border border-dark-border p-3 flex-shrink-0">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Info</h3>
            <div className="space-y-1.5 text-xs text-gray-400">
              {task.platform && (
                <div className="flex justify-between">
                  <span>Platform</span>
                  <span className="text-white capitalize">{task.platform}</span>
                </div>
              )}
              {task.duration > 0 && (
                <div className="flex justify-between">
                  <span>Duration</span>
                  <span className="text-white">{formatDuration(task.duration)}</span>
                </div>
              )}
              {task.style && (
                <div className="flex justify-between">
                  <span>Style</span>
                  <span className="text-white">{task.style}</span>
                </div>
              )}
              {task.model && (
                <div className="flex justify-between">
                  <span>Model</span>
                  <span className="text-white truncate ml-2 max-w-[120px]">{task.model}</span>
                </div>
              )}
              {task.formats?.length > 0 && (
                <div className="flex justify-between">
                  <span>Formats</span>
                  <span className="text-white">{task.formats.join(', ')}</span>
                </div>
              )}
            </div>
          </div>

          {/* TOC */}
          {toc.length > 0 && viewMode === 'markdown' && (
            <div className="bg-dark-surface rounded-xl border border-dark-border p-3 flex-shrink-0">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Contents</h3>
              <nav className="space-y-0.5">
                {toc.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => scrollToHeading(item.slug)}
                    className="block w-full text-left text-xs text-gray-400 hover:text-indigo-400 transition-colors py-0.5 truncate"
                    style={{ paddingLeft: `${(item.level - 1) * 12}px` }}
                    title={item.text}
                  >
                    <ChevronRight size={10} className="inline mr-1 opacity-50" />
                    {item.text}
                  </button>
                ))}
              </nav>
            </div>
          )}
        </aside>

        {/* Right: main content — scrolls independently */}
        <div className="flex-1 min-w-0 overflow-y-auto custom-scrollbar bg-dark-surface rounded-xl border border-dark-border p-4" id="video-content-scroll">
          {!['success', 'failed', 'cancelled'].includes(task.status) && !content ? (
            <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
              <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
              <p className="text-lg text-white font-medium">
                {task.status === 'pending' ? 'Queued for processing...' :
                 task.status === 'downloading' ? 'Downloading video...' :
                 task.status === 'transcribing' ? 'Transcribing audio...' :
                 task.status === 'summarizing' ? 'Generating notes...' :
                 task.status === 'saving' ? 'Saving results...' :
                 'Processing...'}
              </p>
              {task.progress > 0 && (
                <div className="w-48">
                  <div className="h-1.5 bg-dark-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 transition-all duration-500"
                      style={{ width: `${Math.min(task.progress, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{Math.round(task.progress)}%</p>
                </div>
              )}
              {task.message && (
                <p className="text-sm text-gray-400 max-w-md">{task.message}</p>
              )}
            </div>
          ) : (
            <>
              {viewMode === 'markdown' && (
                <MarkdownPreview task={{ ...task, markdown: content }} />
              )}
              {viewMode === 'mindmap' && (
                <MindMapView markdown={content} />
              )}
              {viewMode === 'transcript' && (
                <TranscriptPanel transcript={task.transcript} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
