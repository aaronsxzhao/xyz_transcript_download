import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Copy, Download, Check, FileText, Map, Clock, Loader2,
  ChevronRight, FileDown, RefreshCw, XCircle, ExternalLink, RotateCcw,
  Search, X, CheckCircle, AlertTriangle,
} from 'lucide-react'
import { fetchVideoTask, retryVideoTask, fetchNotionPages, exportToNotion, type VideoTask, type NotionPage } from '../lib/api'
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

  const [notionOpen, setNotionOpen] = useState(false)
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const [notionSearch, setNotionSearch] = useState('')
  const [notionLoading, setNotionLoading] = useState(false)
  const [notionExporting, setNotionExporting] = useState(false)
  const [notionSelectedId, setNotionSelectedId] = useState('')
  const [notionResult, setNotionResult] = useState<{ ok: boolean; message: string; url?: string } | null>(null)
  const notionSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const notionModalRef = useRef<HTMLDivElement>(null)

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
    const md = getCurrentContent()
    if (!md) return
    try {
      const { marked } = await import('marked')
      marked.setOptions({ gfm: true, breaks: false })
      const html = await marked.parse(md)
      const blob = new Blob([html], { type: 'text/html' })
      const textBlob = new Blob([md], { type: 'text/plain' })
      await navigator.clipboard.write([
        new ClipboardItem({ 'text/html': blob, 'text/plain': textBlob }),
      ])
    } catch {
      await navigator.clipboard.writeText(md)
    }
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
      const triggerPrint = () => {
        printWin.focus()
        printWin.print()
      }
      printWin.onload = () => setTimeout(triggerPrint, 500)
      setTimeout(() => { if (!printWin.closed) triggerPrint() }, 2500)
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

  const hasNotionKey = !!localStorage.getItem('notion_api_key')

  const openNotionModal = useCallback(async () => {
    setNotionOpen(true)
    setNotionResult(null)
    setNotionSelectedId('')
    setNotionSearch('')
    setNotionLoading(true)
    try {
      const data = await fetchNotionPages()
      setNotionPages(data.pages)
    } catch (err) {
      setNotionResult({
        ok: false,
        message: err instanceof Error ? err.message : 'Failed to load pages',
      })
    } finally {
      setNotionLoading(false)
    }
  }, [])

  const handleNotionSearch = useCallback((q: string) => {
    setNotionSearch(q)
    if (notionSearchTimeout.current) clearTimeout(notionSearchTimeout.current)
    notionSearchTimeout.current = setTimeout(async () => {
      setNotionLoading(true)
      try {
        const data = await fetchNotionPages(q || undefined)
        setNotionPages(data.pages)
      } catch {
        // keep current pages on search error
      } finally {
        setNotionLoading(false)
      }
    }, 400)
  }, [])

  const handleNotionExport = useCallback(async () => {
    if (!taskId || !notionSelectedId) return
    setNotionExporting(true)
    setNotionResult(null)
    try {
      const result = await exportToNotion(taskId, notionSelectedId)
      setNotionResult({
        ok: true,
        message: `Exported "${result.title}" to Notion`,
        url: result.url,
      })
    } catch (err) {
      setNotionResult({
        ok: false,
        message: err instanceof Error ? err.message : 'Export failed',
      })
    } finally {
      setNotionExporting(false)
    }
  }, [taskId, notionSelectedId])

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
                title="Copy as rich text (paste into Notion)"
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
                <>
                  <button
                    onClick={handleDownloadPdf}
                    disabled={pdfLoading}
                    className="p-1.5 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                    title="Download PDF"
                  >
                    {pdfLoading ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
                  </button>
                  <button
                    onClick={openNotionModal}
                    className="p-1.5 text-gray-400 hover:text-orange-400 transition-colors"
                    title="Send to Notion"
                  >
                    <svg width="14" height="14" viewBox="0 0 100 100" fill="currentColor">
                      <path d="M6.6 12.3c4.2 3.1 5.8 2.9 13.7 2.1l49.5-3.7c1.6 0 .3-1.6-.3-1.8l-8.2-6c-2.4-1.8-5.5-3.9-11.5-3.4L2.7 3.1C-.5 3.4-1.3 5.1.8 6.8zm4.5 14.7v52c0 2.8 1.4 3.8 4.5 3.6l54.4-3.2c3.2-.2 3.5-2.1 3.5-4.3V23.4c0-2.2-.9-3.4-2.8-3.2L15.8 23.3c-2.1.2-2.8 1.2-2.8 3.2v.5zM64 27c.3 1.4 0 2.8-1.4 3l-2.6.5v38.4c-2.3 1.2-4.4 1.9-6.2 1.9-2.8 0-3.5-.9-5.6-3.5L31.6 40.3v24.4l5.4 1.2s0 2.8-3.9 2.8l-10.8.6c-.3-.6 0-2.2 1.1-2.4l2.8-.8V33.7l-3.9-.3c-.3-1.4.5-3.5 2.8-3.7l11.6-.7 17.2 26.3V33l-4.5-.5c-.3-1.6 1-2.8 2.6-2.9l11.1-.6zM2.2 1.7l50.3-3.8c6.2-.5 7.8-.2 11.6 2.8l16 11.2c2.6 1.9 3.5 2.4 3.5 4.5V78c0 4.3-1.6 6.8-7.1 7.2L18.5 88.6c-4.1.2-6.1-.4-8.2-3.1L1.6 74.3C-.3 71.6-1 69.7-1 67.2v-60c0-3.4 1.6-6.2 5.1-5.5z" transform="translate(10 5) scale(0.9)"/>
                    </svg>
                  </button>
                </>
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

      {/* Notion export modal */}
      {notionOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setNotionOpen(false) }}
        >
          <div
            ref={notionModalRef}
            className="bg-dark-surface border border-dark-border rounded-2xl w-full max-w-md mx-4 shadow-2xl"
          >
            <div className="flex items-center justify-between p-4 border-b border-dark-border">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 100 100" fill="currentColor" className="text-orange-400">
                  <path d="M6.6 12.3c4.2 3.1 5.8 2.9 13.7 2.1l49.5-3.7c1.6 0 .3-1.6-.3-1.8l-8.2-6c-2.4-1.8-5.5-3.9-11.5-3.4L2.7 3.1C-.5 3.4-1.3 5.1.8 6.8zm4.5 14.7v52c0 2.8 1.4 3.8 4.5 3.6l54.4-3.2c3.2-.2 3.5-2.1 3.5-4.3V23.4c0-2.2-.9-3.4-2.8-3.2L15.8 23.3c-2.1.2-2.8 1.2-2.8 3.2v.5zM64 27c.3 1.4 0 2.8-1.4 3l-2.6.5v38.4c-2.3 1.2-4.4 1.9-6.2 1.9-2.8 0-3.5-.9-5.6-3.5L31.6 40.3v24.4l5.4 1.2s0 2.8-3.9 2.8l-10.8.6c-.3-.6 0-2.2 1.1-2.4l2.8-.8V33.7l-3.9-.3c-.3-1.4.5-3.5 2.8-3.7l11.6-.7 17.2 26.3V33l-4.5-.5c-.3-1.6 1-2.8 2.6-2.9l11.1-.6zM2.2 1.7l50.3-3.8c6.2-.5 7.8-.2 11.6 2.8l16 11.2c2.6 1.9 3.5 2.4 3.5 4.5V78c0 4.3-1.6 6.8-7.1 7.2L18.5 88.6c-4.1.2-6.1-.4-8.2-3.1L1.6 74.3C-.3 71.6-1 69.7-1 67.2v-60c0-3.4 1.6-6.2 5.1-5.5z" transform="translate(10 5) scale(0.9)"/>
                </svg>
                Send to Notion
              </h2>
              <button
                onClick={() => setNotionOpen(false)}
                className="p-1 text-gray-400 hover:text-white transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-4 space-y-3">
              {!hasNotionKey ? (
                <div className="space-y-3 py-2">
                  <p className="text-sm text-gray-300">Set up your Notion integration to export notes.</p>
                  <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
                    <li>Go to <a href="https://www.notion.so/profile/integrations" target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:text-orange-300">Notion Integrations <ExternalLink size={10} className="inline" /></a></li>
                    <li>Create an integration and copy the token</li>
                    <li>Go to <Link to="/settings" className="text-orange-400 hover:text-orange-300">Settings</Link> and paste it in the Notion section</li>
                    <li>Share target pages with your integration in Notion</li>
                  </ol>
                </div>
              ) : (
              <>
              {/* Search */}
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={notionSearch}
                  onChange={e => handleNotionSearch(e.target.value)}
                  placeholder="Search pages..."
                  className="w-full pl-9 pr-3 py-2 bg-dark-hover border border-dark-border text-white text-sm rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  autoFocus
                />
              </div>

              {/* Page list */}
              <div className="max-h-60 overflow-y-auto custom-scrollbar space-y-0.5">
                {notionLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin text-gray-500" />
                  </div>
                ) : notionPages.length === 0 ? (
                  <div className="text-center py-8 text-sm text-gray-500">
                    {notionResult?.ok === false
                      ? 'Could not load pages'
                      : 'No pages found. Share pages with your integration in Notion.'}
                  </div>
                ) : (
                  notionPages.map(page => (
                    <button
                      key={page.id}
                      onClick={() => setNotionSelectedId(page.id === notionSelectedId ? '' : page.id)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                        page.id === notionSelectedId
                          ? 'bg-orange-500/15 border border-orange-500/40 text-white'
                          : 'hover:bg-dark-hover text-gray-300 border border-transparent'
                      }`}
                    >
                      <span className="flex-shrink-0 w-5 text-center">
                        {page.icon || '📄'}
                      </span>
                      <span className="truncate flex-1">{page.title || 'Untitled'}</span>
                      {page.id === notionSelectedId && (
                        <CheckCircle size={14} className="text-orange-400 flex-shrink-0" />
                      )}
                    </button>
                  ))
                )}
              </div>

              </>
              )}

              {/* Result message */}
              {notionResult && (
                <div className={`p-2.5 rounded-lg text-xs ${
                  notionResult.ok
                    ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                    : 'bg-red-500/10 border border-red-500/30 text-red-400'
                }`}>
                  {notionResult.ok ? <CheckCircle size={12} className="inline mr-1.5" /> : <AlertTriangle size={12} className="inline mr-1.5" />}
                  {notionResult.message}
                  {notionResult.url && (
                    <a
                      href={notionResult.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-2 inline-flex items-center gap-1 text-orange-400 hover:text-orange-300"
                    >
                      Open in Notion <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 p-4 border-t border-dark-border">
              <button
                onClick={() => setNotionOpen(false)}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
              >
                {notionResult?.ok ? 'Done' : hasNotionKey ? 'Cancel' : 'Close'}
              </button>
              {hasNotionKey && !notionResult?.ok && (
                <button
                  onClick={handleNotionExport}
                  disabled={!notionSelectedId || notionExporting}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {notionExporting ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
                  Export
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
