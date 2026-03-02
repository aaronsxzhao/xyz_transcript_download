import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { 
  ArrowLeft, 
  FileText, 
  MessageSquare, 
  Tag, 
  CheckCircle, 
  Quote,
  ChevronDown,
  ChevronUp,
  Loader2,
  ExternalLink,
  RefreshCw,
  Copy,
  Check,
  Download,
  FileDown,
  Search,
  X,
  AlertTriangle,
} from 'lucide-react'
import { fetchSummary, fetchTranscript, resummarizeEpisode, fetchNotionPages, exportMarkdownToNotion, type Summary, type Transcript, type KeyPoint, type TranscriptSegment, type NotionPage } from '../lib/api'
import { getAccessToken } from '../lib/auth'
import { useStore } from '../lib/store'

type Tab = 'summary' | 'transcript'

function summaryToMarkdown(summary: Summary): string {
  const lines: string[] = []
  lines.push(`# ${summary.title}`)
  lines.push('')

  if (summary.overview) {
    lines.push('## Overview')
    lines.push('')
    lines.push(summary.overview)
    lines.push('')
  }

  const byTopic: Record<string, KeyPoint[]> = {}
  for (const kp of summary.key_points) {
    if (!byTopic[kp.topic]) byTopic[kp.topic] = []
    byTopic[kp.topic].push(kp)
  }

  if (Object.keys(byTopic).length > 0) {
    lines.push('## Key Points')
    lines.push('')
    for (const [topic, points] of Object.entries(byTopic)) {
      lines.push(`### ${topic}`)
      lines.push('')
      for (const kp of points) {
        lines.push(`- **${kp.summary}**`)
        if (kp.original_quote) {
          lines.push(`  > ${kp.original_quote}`)
        }
        lines.push('')
      }
    }
  }

  if (summary.takeaways.length > 0) {
    lines.push('## Takeaways')
    lines.push('')
    for (const t of summary.takeaways) {
      lines.push(`- ${t}`)
    }
    lines.push('')
  }

  return lines.join('\n')
}

export default function Viewer() {
  const { eid } = useParams<{ eid: string }>()
  const [activeTab, setActiveTab] = useState<Tab>('summary')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [loading, setLoading] = useState(true)
  const [resummarizing, setResummarizing] = useState(false)
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set())
  const [copied, setCopied] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)

  const [notionOpen, setNotionOpen] = useState(false)
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const [notionSearch, setNotionSearch] = useState('')
  const [notionLoading, setNotionLoading] = useState(false)
  const [notionExporting, setNotionExporting] = useState(false)
  const [notionSelectedId, setNotionSelectedId] = useState('')
  const [notionResult, setNotionResult] = useState<{ ok: boolean; message: string; url?: string } | null>(null)
  const notionSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  
  useEffect(() => {
    if (eid) loadData()
  }, [eid])
  
  async function loadData() {
    setLoading(true)
    try {
      const [summaryData, transcriptData] = await Promise.allSettled([
        fetchSummary(eid!),
        fetchTranscript(eid!),
      ])
      
      if (summaryData.status === 'fulfilled') {
        setSummary(summaryData.value)
        if (summaryData.value.topics.length > 0) {
          setExpandedTopics(new Set([summaryData.value.topics[0]]))
        }
      }
      if (transcriptData.status === 'fulfilled') {
        setTranscript(transcriptData.value)
      }
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }
  
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { updateJob } = useStore()

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  async function handleResummarize() {
    if (!eid || resummarizing) return
    
    try {
      setResummarizing(true)
      setSummary(null)
      const result = await resummarizeEpisode(eid)

      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Re-summarizing...',
        episode_id: eid,
        episode_title: summary?.title || '',
      })

      pollRef.current = setInterval(async () => {
        try {
          const newSummary = await fetchSummary(eid)
          if (newSummary && newSummary.topics && newSummary.topics.length > 0) {
            setSummary(newSummary)
            setResummarizing(false)
            if (newSummary.topics.length > 0) {
              setExpandedTopics(new Set([newSummary.topics[0]]))
            }
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          }
        } catch {
          // Summary not ready yet, keep polling
        }
      }, 5000)
    } catch (err) {
      console.error('Failed to start re-summarization:', err)
      alert('Failed to start re-summarization')
      setResummarizing(false)
    }
  }

  const getMarkdown = (): string => {
    if (!summary) return ''
    return summaryToMarkdown(summary)
  }

  const handleCopy = async () => {
    const md = getMarkdown()
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

  const handleDownloadMd = () => {
    const md = getMarkdown()
    if (!md) return
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${summary?.title || 'summary'}.md`
    document.body.appendChild(a)
    a.click()
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url) }, 100)
  }

  const handleDownloadPdf = async () => {
    const md = getMarkdown()
    if (!md || pdfLoading) return
    setPdfLoading(true)
    try {
      const { marked } = await import('marked')
      marked.setOptions({ gfm: true, breaks: false })
      const body = await marked.parse(md)
      const printWin = window.open('', '_blank', 'width=800,height=600')
      if (!printWin) { alert('Please allow popups to download PDF'); return }
      printWin.document.write(`<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>${summary?.title || 'Summary'}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; background: #fff; padding: 20px 30px; font-size: 13px; line-height: 1.75; }
  h1 { font-size: 22px; font-weight: 700; color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; margin: 24px 0 16px; }
  h2 { font-size: 18px; font-weight: 700; color: #1e40af; margin: 28px 0 12px; }
  h3 { font-size: 15px; font-weight: 600; color: #1f2937; margin: 20px 0 8px; }
  p { font-size: 13px; line-height: 1.75; color: #374151; margin: 8px 0; }
  li { font-size: 13px; line-height: 1.75; color: #374151; }
  ul, ol { padding-left: 20px; margin: 6px 0; }
  strong { color: #111827; }
  blockquote { border-left: 3px solid #6366f1; background: #eef2ff; color: #374151; padding: 10px 16px; margin: 12px 0; border-radius: 0 6px 6px 0; font-size: 13px; }
  blockquote p { margin: 4px 0; }
  @media print { body { padding: 0; } h1, h2, h3 { page-break-after: avoid; } }
</style>
</head><body>${body}</body></html>`)
      printWin.document.close()
      const triggerPrint = () => { printWin.focus(); printWin.print() }
      printWin.onload = () => setTimeout(triggerPrint, 500)
      setTimeout(() => { if (!printWin.closed) triggerPrint() }, 2500)
    } catch (e) {
      console.error('PDF generation failed:', e)
    } finally {
      setPdfLoading(false)
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
      setNotionResult({ ok: false, message: err instanceof Error ? err.message : 'Failed to load pages' })
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
      } catch { /* keep current pages */ }
      finally { setNotionLoading(false) }
    }, 400)
  }, [])

  const handleNotionExport = useCallback(async () => {
    if (!summary || !notionSelectedId) return
    setNotionExporting(true)
    setNotionResult(null)
    try {
      const md = summaryToMarkdown(summary)
      const result = await exportMarkdownToNotion(md, summary.title, notionSelectedId)
      setNotionResult({ ok: true, message: `Exported "${result.title}" to Notion`, url: result.url })
    } catch (err) {
      setNotionResult({ ok: false, message: err instanceof Error ? err.message : 'Export failed' })
    } finally {
      setNotionExporting(false)
    }
  }, [summary, notionSelectedId])
  
  function toggleTopic(topic: string) {
    const newExpanded = new Set(expandedTopics)
    if (newExpanded.has(topic)) {
      newExpanded.delete(topic)
    } else {
      newExpanded.add(topic)
    }
    setExpandedTopics(newExpanded)
  }
  
  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }
  
  const keyPointsByTopic = summary?.key_points.reduce((acc: Record<string, KeyPoint[]>, kp: KeyPoint) => {
    if (!acc[kp.topic]) acc[kp.topic] = []
    acc[kp.topic].push(kp)
    return acc
  }, {} as Record<string, KeyPoint[]>) || {}
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }
  
  return (
    <div className="space-y-4 md:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
        <div className="flex items-start gap-3">
          <Link
            to="/"
            className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
          >
            <ArrowLeft size={20} />
          </Link>
          <div className="flex-1 min-w-0 sm:hidden">
            <h1 className="text-lg font-bold text-white line-clamp-2">
              {summary?.title || 'Episode Viewer'}
            </h1>
          </div>
        </div>
        
        <div className="flex-1 min-w-0 hidden sm:block">
          <h1 className="text-xl md:text-2xl font-bold text-white mb-2 line-clamp-2">
            {summary?.title || 'Episode Viewer'}
          </h1>
          <div className="flex flex-wrap items-center gap-2 md:gap-4">
            {summary && (
              <>
                <span className="flex items-center gap-1.5 text-xs md:text-sm text-gray-400">
                  <Tag size={14} />
                  {summary.topics.length} topics
                </span>
                <span className="flex items-center gap-1.5 text-xs md:text-sm text-gray-400">
                  <MessageSquare size={14} />
                  {summary.key_points.length} key points
                </span>
              </>
            )}
            {transcript && (
              <span className="flex items-center gap-1.5 text-xs md:text-sm text-gray-400">
                <FileText size={14} />
                {formatTime(transcript.duration)}
              </span>
            )}
          </div>
        </div>
        
        {/* Action buttons */}
        <div className="flex items-center gap-1.5 sm:flex-shrink-0">
          {summary && (
            <>
              <button
                onClick={handleCopy}
                className="p-2 text-gray-400 hover:text-white transition-colors"
                title="Copy as rich text (paste into Notion)"
              >
                {copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
              </button>
              <button
                onClick={handleDownloadMd}
                className="p-2 text-gray-400 hover:text-white transition-colors"
                title="Download .md"
              >
                <Download size={16} />
              </button>
              <button
                onClick={handleDownloadPdf}
                disabled={pdfLoading}
                className="p-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                title="Download PDF"
              >
                {pdfLoading ? <Loader2 size={16} className="animate-spin" /> : <FileDown size={16} />}
              </button>
              <button
                onClick={openNotionModal}
                className="p-2 text-gray-400 hover:text-orange-400 transition-colors"
                title="Send to Notion"
              >
                <svg width="16" height="16" viewBox="0 0 100 100" fill="currentColor">
                  <path d="M6.6 12.3c4.2 3.1 5.8 2.9 13.7 2.1l49.5-3.7c1.6 0 .3-1.6-.3-1.8l-8.2-6c-2.4-1.8-5.5-3.9-11.5-3.4L2.7 3.1C-.5 3.4-1.3 5.1.8 6.8zm4.5 14.7v52c0 2.8 1.4 3.8 4.5 3.6l54.4-3.2c3.2-.2 3.5-2.1 3.5-4.3V23.4c0-2.2-.9-3.4-2.8-3.2L15.8 23.3c-2.1.2-2.8 1.2-2.8 3.2v.5zM64 27c.3 1.4 0 2.8-1.4 3l-2.6.5v38.4c-2.3 1.2-4.4 1.9-6.2 1.9-2.8 0-3.5-.9-5.6-3.5L31.6 40.3v24.4l5.4 1.2s0 2.8-3.9 2.8l-10.8.6c-.3-.6 0-2.2 1.1-2.4l2.8-.8V33.7l-3.9-.3c-.3-1.4.5-3.5 2.8-3.7l11.6-.7 17.2 26.3V33l-4.5-.5c-.3-1.6 1-2.8 2.6-2.9l11.1-.6zM2.2 1.7l50.3-3.8c6.2-.5 7.8-.2 11.6 2.8l16 11.2c2.6 1.9 3.5 2.4 3.5 4.5V78c0 4.3-1.6 6.8-7.1 7.2L18.5 88.6c-4.1.2-6.1-.4-8.2-3.1L1.6 74.3C-.3 71.6-1 69.7-1 67.2v-60c0-3.4 1.6-6.2 5.1-5.5z" transform="translate(10 5) scale(0.9)"/>
                </svg>
              </button>
            </>
          )}
          <button
            onClick={handleResummarize}
            disabled={resummarizing || !transcript}
            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-sm transition-colors text-white"
            title="Regenerate summary using existing transcript"
          >
            <RefreshCw size={16} className={resummarizing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">{resummarizing ? 'Processing...' : 'Re-summarize'}</span>
          </button>
          <a
            href={`/api/summaries/${eid}/html${getAccessToken() ? `?token=${getAccessToken()}` : ''}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover text-sm transition-colors"
          >
            <ExternalLink size={16} />
            <span className="hidden sm:inline">HTML</span>
          </a>
        </div>
      </div>
      
      {/* Mobile stats */}
      <div className="flex flex-wrap items-center gap-3 sm:hidden text-xs text-gray-400">
        {summary && (
          <>
            <span className="flex items-center gap-1">
              <Tag size={12} />
              {summary.topics.length} topics
            </span>
            <span className="flex items-center gap-1">
              <MessageSquare size={12} />
              {summary.key_points.length} points
            </span>
          </>
        )}
        {transcript && (
          <span className="flex items-center gap-1">
            <FileText size={12} />
            {formatTime(transcript.duration)}
          </span>
        )}
      </div>
      
      {/* Tabs */}
      <div className="flex gap-1 md:gap-2 border-b border-dark-border">
        <button
          onClick={() => setActiveTab('summary')}
          className={`flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2.5 md:py-3 border-b-2 transition-colors text-sm md:text-base ${
            activeTab === 'summary'
              ? 'border-indigo-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <MessageSquare size={16} className="md:w-[18px] md:h-[18px]" />
          Summary
        </button>
        <button
          onClick={() => setActiveTab('transcript')}
          disabled={!transcript}
          className={`flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2.5 md:py-3 border-b-2 transition-colors text-sm md:text-base disabled:opacity-50 disabled:cursor-not-allowed ${
            activeTab === 'transcript'
              ? 'border-indigo-500 text-white'
              : 'border-transparent text-gray-400 hover:text-white'
          }`}
        >
          <FileText size={18} />
          Transcript
        </button>
      </div>
      
      {/* Content */}
      {activeTab === 'summary' && resummarizing && !summary && (
        <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
          <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
          <p className="text-lg text-white font-medium">Re-generating summary...</p>
          <p className="text-sm text-gray-400">This may take a minute. The page will update automatically when done.</p>
        </div>
      )}

      {activeTab === 'summary' && summary && (
        <div className="space-y-6">
          {/* Overview */}
          <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="text-indigo-500" size={20} />
              Overview
            </h2>
            <p className="text-gray-300 whitespace-pre-line leading-relaxed">
              {summary.overview}
            </p>
          </div>
          
          {/* Topics/Key Points */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <MessageSquare className="text-purple-500" size={20} />
              Key Points by Topic
            </h2>
            
            {(Object.entries(keyPointsByTopic) as [string, KeyPoint[]][]).map(([topic, points]) => (
              <div
                key={topic}
                className="bg-dark-surface border border-dark-border rounded-xl overflow-hidden"
              >
                <button
                  onClick={() => toggleTopic(topic)}
                  className="w-full flex items-center justify-between p-4 hover:bg-dark-hover transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Tag className="text-indigo-400" size={18} />
                    <span className="font-medium text-white">{topic}</span>
                    <span className="text-sm text-gray-500">
                      ({points.length} points)
                    </span>
                  </div>
                  {expandedTopics.has(topic) ? (
                    <ChevronUp size={20} className="text-gray-400" />
                  ) : (
                    <ChevronDown size={20} className="text-gray-400" />
                  )}
                </button>
                
                {expandedTopics.has(topic) && (
                  <div className="border-t border-dark-border p-4 space-y-4">
                    {points.map((kp, idx) => (
                      <div key={idx} className="pl-4 border-l-2 border-indigo-500/50">
                        <p className="text-gray-200 mb-2">{kp.summary}</p>
                        {kp.original_quote && (
                          <div className="flex items-start gap-2 p-3 bg-dark-hover rounded-lg">
                            <Quote className="text-gray-500 flex-shrink-0 mt-0.5" size={16} />
                            <p className="text-sm text-gray-400 italic">
                              {kp.original_quote}
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          
          {/* Takeaways */}
          {summary.takeaways.length > 0 && (
            <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle className="text-green-500" size={20} />
                Takeaways
              </h2>
              <ul className="space-y-3">
                {summary.takeaways.map((takeaway: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-3">
                    <CheckCircle className="text-green-500 flex-shrink-0 mt-0.5" size={16} />
                    <span className="text-gray-300">{takeaway}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      
      {activeTab === 'transcript' && transcript && (
        <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <FileText className="text-blue-500" size={20} />
            Full Transcript
          </h2>
          
          {transcript.segments.length > 0 ? (
            <div className="space-y-4 max-h-[600px] overflow-y-auto">
              {transcript.segments.map((seg: TranscriptSegment, idx: number) => (
                <div key={idx} className="flex gap-4">
                  <span className="text-xs text-gray-500 font-mono w-12 flex-shrink-0 pt-0.5">
                    {formatTime(seg.start)}
                  </span>
                  <p className="text-gray-300">{seg.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-300 whitespace-pre-line leading-relaxed">
              {transcript.text}
            </p>
          )}
        </div>
      )}
      
      {!summary && !transcript && (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <FileText className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No content available</p>
          <p className="text-gray-500">Process this episode to generate transcript and summary</p>
        </div>
      )}

      {/* Notion export modal */}
      {notionOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setNotionOpen(false) }}
        >
          <div className="bg-dark-surface border border-dark-border rounded-2xl w-full max-w-md mx-4 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-dark-border">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 100 100" fill="currentColor" className="text-orange-400">
                  <path d="M6.6 12.3c4.2 3.1 5.8 2.9 13.7 2.1l49.5-3.7c1.6 0 .3-1.6-.3-1.8l-8.2-6c-2.4-1.8-5.5-3.9-11.5-3.4L2.7 3.1C-.5 3.4-1.3 5.1.8 6.8zm4.5 14.7v52c0 2.8 1.4 3.8 4.5 3.6l54.4-3.2c3.2-.2 3.5-2.1 3.5-4.3V23.4c0-2.2-.9-3.4-2.8-3.2L15.8 23.3c-2.1.2-2.8 1.2-2.8 3.2v.5zM64 27c.3 1.4 0 2.8-1.4 3l-2.6.5v38.4c-2.3 1.2-4.4 1.9-6.2 1.9-2.8 0-3.5-.9-5.6-3.5L31.6 40.3v24.4l5.4 1.2s0 2.8-3.9 2.8l-10.8.6c-.3-.6 0-2.2 1.1-2.4l2.8-.8V33.7l-3.9-.3c-.3-1.4.5-3.5 2.8-3.7l11.6-.7 17.2 26.3V33l-4.5-.5c-.3-1.6 1-2.8 2.6-2.9l11.1-.6zM2.2 1.7l50.3-3.8c6.2-.5 7.8-.2 11.6 2.8l16 11.2c2.6 1.9 3.5 2.4 3.5 4.5V78c0 4.3-1.6 6.8-7.1 7.2L18.5 88.6c-4.1.2-6.1-.4-8.2-3.1L1.6 74.3C-.3 71.6-1 69.7-1 67.2v-60c0-3.4 1.6-6.2 5.1-5.5z" transform="translate(10 5) scale(0.9)"/>
                </svg>
                Send to Notion
              </h2>
              <button onClick={() => setNotionOpen(false)} className="p-1 text-gray-400 hover:text-white transition-colors">
                <X size={16} />
              </button>
            </div>

            <div className="p-4 space-y-3">
              {!hasNotionKey ? (
                <div className="space-y-3 py-2">
                  <p className="text-sm text-gray-300">Set up your Notion integration to export summaries.</p>
                  <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
                    <li>Go to <a href="https://www.notion.so/profile/integrations" target="_blank" rel="noopener noreferrer" className="text-orange-400 hover:text-orange-300">Notion Integrations <ExternalLink size={10} className="inline" /></a></li>
                    <li>Create an integration and copy the token</li>
                    <li>Go to <Link to="/settings" className="text-orange-400 hover:text-orange-300">Settings</Link> and paste it in the Notion section</li>
                    <li>Share target pages with your integration in Notion</li>
                  </ol>
                </div>
              ) : (
              <>
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
                      <span className="flex-shrink-0 w-5 text-center">{page.icon || '📄'}</span>
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

              {notionResult && (
                <div className={`p-2.5 rounded-lg text-xs ${
                  notionResult.ok
                    ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                    : 'bg-red-500/10 border border-red-500/30 text-red-400'
                }`}>
                  {notionResult.ok ? <CheckCircle size={12} className="inline mr-1.5" /> : <AlertTriangle size={12} className="inline mr-1.5" />}
                  {notionResult.message}
                  {notionResult.url && (
                    <a href={notionResult.url} target="_blank" rel="noopener noreferrer" className="ml-2 inline-flex items-center gap-1 text-orange-400 hover:text-orange-300">
                      Open in Notion <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 p-4 border-t border-dark-border">
              <button onClick={() => setNotionOpen(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
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
