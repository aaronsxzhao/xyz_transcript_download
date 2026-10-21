import { useWarmCache } from '../lib/cache'
import { printHtml } from '../lib/print'
import SummaryText from '../components/SummaryText'
import ReaderControls from '../components/ReaderControls'
import { useReadingPosition, useDialog } from '../lib/reading'
import LoadError from '../components/LoadError'
import { deferView } from '../components/DeferredView'
const TranscriptSegments = deferView(()=>import('../components/TranscriptSegments'))
import { escapeHtml, markdownToSafeHtml } from '../lib/safeHtml'
import { getPreference } from '../lib/preferences'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
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
import { ApiError, fetchJob, fetchSummary, fetchTranscript, resummarizeEpisode, fetchNotionPages, exportMarkdownToNotion, type Summary, type Transcript, type KeyPoint, type NotionPage } from '../lib/api'
import { getAccessToken } from '../lib/auth'
import { useStore } from '../lib/store'
import { getCache, setCache, CacheKeys } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { usePageTiming } from '../lib/pageTiming'

type Tab = 'summary' | 'transcript'

function summaryToMarkdown(summary: Summary, transcript?: Transcript | null): string {
  const lines: string[] = []
  lines.push(`# ${summary.title}`)
  lines.push('')

  const metadata: string[] = []
  if (summary.topics.length > 0) metadata.push(`- Topics: ${summary.topics.length}`)
  if (summary.key_points.length > 0) metadata.push(`- Key points: ${summary.key_points.length}`)
  if (transcript?.duration) {
    const mins = Math.floor(transcript.duration / 60)
    const secs = Math.floor(transcript.duration % 60)
    metadata.push(`- Duration: ${mins}:${secs.toString().padStart(2, '0')}`)
  }

  if (metadata.length > 0) {
    lines.push('## Details')
    lines.push('')
    lines.push(...metadata)
    lines.push('')
  }

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
  const navigate = useNavigate()
  const currentEid = useRef(eid)
  currentEid.current = eid
  const [activeTab, setActiveTab] = useState<Tab>('summary')
  const [summary, setSummary] = useState<Summary | null>(() => getCache(CacheKeys.SUMMARY(eid!)))
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [loading, setLoading] = useState(() => !getCache(CacheKeys.SUMMARY(eid!)))
  useWarmCache<Summary>(CacheKeys.SUMMARY(eid!), value => {setSummary(value);setLoading(false)})
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [resummarizing, setResummarizing] = useState(false)
  const [error, setError] = useState('')
  usePageTiming('viewer', !loading && (summary?.episode_id === eid || transcript?.episode_id === eid), CacheKeys.SUMMARY(eid!), !!error && !loading)
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(() => new Set(getCache<Summary>(CacheKeys.SUMMARY(eid!))?.topics.slice(0, 1)))
  const [copied, setCopied] = useState(false)
  const [copying, setCopying] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)

  useReadingPosition(`podcast:${eid}`, undefined, !loading)
  const [notionOpen, setNotionOpen] = useState(false)
  useDialog(notionOpen, () => setNotionOpen(false))
  const [notionPages, setNotionPages] = useState<NotionPage[]>([])
  const [notionSearch, setNotionSearch] = useState('')
  const [notionLoading, setNotionLoading] = useState(false)
  const [notionExporting, setNotionExporting] = useState(false)
  const [notionSelectedId, setNotionSelectedId] = useState('')
  const [notionResult, setNotionResult] = useState<{ ok: boolean; message: string; url?: string } | null>(null)
  const notionSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  
  const loadTranscript = useCallback(async () => {
    const requestedEid = eid
    setTranscriptLoading(true)
    try {
      const data = await fetchTranscript(eid!)
      if (requestedEid === currentEid.current) setTranscript(data)
      return data
    } catch {
      if (requestedEid === currentEid.current) setError('Cannot load the transcript. Please retry.')
      return null
    } finally {
      if (requestedEid === currentEid.current) setTranscriptLoading(false)
    }
  }, [eid])

  useEffect(() => {
    if (!eid) return
    const cached = getCache<Summary>(CacheKeys.SUMMARY(eid))
    setSummary(cached)
    setExpandedTopics(new Set(cached?.topics.slice(0, 1)))
    setTranscript(null)
    setActiveTab('summary')
    setResummarizing(false)
    void loadData()
  }, [eid])

  useEffect(() => {
    if (activeTab === 'transcript' && !transcript) void loadTranscript()
  }, [activeTab, transcript, loadTranscript])
  
  async function loadData() {
    const cached = getCache<Summary>(CacheKeys.SUMMARY(eid!))
    setLoading(!cached)
    setError('')
    const requestedEid = eid
    const owner = getAccountId()
    try {
      const data = await fetchSummary(eid!)
      if (requestedEid !== currentEid.current || owner !== getAccountId()) return
      setSummary(data)
      setCache(CacheKeys.SUMMARY(eid!), data, owner)
      setExpandedTopics(new Set(data.topics.slice(0, 1)))
    } catch (err) {
      if (requestedEid !== currentEid.current || owner !== getAccountId()) return
      if (cached) setError('Cannot refresh this summary. Please retry.')
      else if (err instanceof ApiError && err.status === 404) {
        // Episodes with a transcript but no summary still open normally.
        const fallback = await loadTranscript()
        if (requestedEid !== currentEid.current) return
        if (fallback) setActiveTab('transcript')
        else setError('Cannot load this episode. Please retry.')
      } else setError(err instanceof Error ? err.message : 'Cannot load this summary. Please retry.')
    } finally {
      if (requestedEid === currentEid.current) setLoading(false)
    }
  }
  
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { updateJob } = useStore()

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [eid])

  async function handleResummarize() {
    if (!eid || resummarizing) return
    
    try {
      setResummarizing(true)
      setError('')
      const result = await resummarizeEpisode(eid)

      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Re-summarizing...',
        episode_id: eid,
        episode_title: summary?.title || '',
      })

      let polling = false
      pollRef.current = setInterval(async () => {
        if (polling || eid !== currentEid.current) return
        polling = true
        try {
          const job = await fetchJob(result.job_id)
          if (eid !== currentEid.current) return
          updateJob(job)
          if (job.status === 'completed') {
            const fresh = await fetchSummary(eid)
            if (eid !== currentEid.current) return
            setSummary(fresh)
            setCache(CacheKeys.SUMMARY(eid), fresh)
            setExpandedTopics(new Set(fresh.topics.slice(0, 1)))
            setResummarizing(false)
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          } else if (['failed', 'cancelled'].includes(job.status)) {
            setError(job.message || 'Re-summarization did not complete. Your previous summary is still available.')
            setResummarizing(false)
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          }
        } catch { /* Keep polling through temporary connection failures. */ }
        finally { polling = false }
      }, 3000)
    } catch (err) {
      console.error('Failed to start re-summarization:', err)
      setError('Could not start re-summarization. Your previous summary is still available.')
      setResummarizing(false)
    }
  }

  const getMarkdown = (): string => {
    if (!summary) return ''
    return summaryToMarkdown(summary, transcript)
  }

  const handleCopy = async () => {
    const md = getMarkdown()
    if (!md || copying) return
    setCopying(true)
    try {
      try {
        // Passing promised HTML keeps clipboard permission tied to the click
        // on Safari, even while the formatter module is still downloading.
        const html = markdownToSafeHtml(md).then(value => new Blob([value], { type: 'text/html' }))
        void html.catch(() => {})
        await navigator.clipboard.write([new ClipboardItem({ 'text/html': html, 'text/plain': new Blob([md], {type:'text/plain'}) })])
      } catch { await navigator.clipboard.writeText(md) }
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { setError('Copy failed. Please allow clipboard access or download the Markdown file.') }
    finally { setCopying(false) }
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
      const body = await markdownToSafeHtml(md)
      const html = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: http: data: blob:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>${escapeHtml(summary?.title || 'Summary')}</title>
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
</head><body>${body}</body></html>`
      await printHtml(html)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not prepare the PDF. Please retry or download Markdown.')
    } finally {
      setPdfLoading(false)
    }
  }

  const hasNotionKey = !!getPreference('notion_api_key')

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
      const md = summaryToMarkdown(summary, transcript)
      const result = await exportMarkdownToNotion(md, summary.title, notionSelectedId)
      setNotionResult({ ok: true, message: `Exported "${result.title}" to Notion`, url: result.url })
    } catch (err) {
      setNotionResult({ ok: false, message: err instanceof Error ? err.message : 'Export failed' })
    } finally {
      setNotionExporting(false)
    }
  }, [notionSelectedId, summary, transcript])
  
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
  
  const topicEntries = Object.entries(keyPointsByTopic) as [string, KeyPoint[]][]

  const [activeSection,setActiveSection] = useState('summary-overview')
  useEffect(() => {
    if (loading || activeTab !== 'summary') return
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a,b) => a.boundingClientRect.top-b.boundingClientRect.top)
      if (visible[0]) setActiveSection(visible[0].target.id)
    }, {rootMargin:'-80px 0px -60% 0px'})
    document.querySelectorAll('[id^="summary-topic-"], #summary-overview, #summary-key-points, #summary-takeaways').forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [summary, loading, activeTab])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }
  
  return (
    <div className="reader-body podcast-reader space-y-4 md:space-y-6">
      {error && <LoadError message={error} onRetry={() => {
        setError('')
        if (activeTab === 'transcript') void loadTranscript()
        else void loadData()
      }} />}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
        <div className="flex items-start gap-3">
          <button
            aria-label="Go back"
            onClick={() => navigate(-1)}
            className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex-1 min-w-0 sm:hidden">
            <h1 className="page-title text-lg font-bold text-white line-clamp-2">
              {summary?.title || 'Episode Viewer'}
            </h1>
          </div>
        </div>
        
        <div className="flex-1 min-w-0 hidden sm:block">
          <h1 className="page-title text-xl md:text-2xl font-bold text-white mb-2 line-clamp-2">
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
        <div className="reader-actions" role="group" aria-label="Note actions">
          {summary && (
            <>
              <button
                onClick={handleCopy}
                disabled={copying}
                aria-label={copying ? 'Copying note' : copied ? 'Copied' : 'Copy note'}
                className="p-2 text-gray-400 hover:text-white transition-colors"
                title="Copy as rich text (paste into Notion)"
              >
                {copying ? <Loader2 size={14} className="animate-spin" /> : copied ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
              </button>
              <details className="reader-export" onKeyDown={e => { if (e.key === 'Escape') { e.currentTarget.open = false; e.currentTarget.querySelector('summary')?.focus() } }} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) e.currentTarget.open = false }}>
                <summary>Export</summary>
                <div className="reader-export-panel">
              <button
                onClick={handleDownloadMd}
                className="p-2 text-gray-400 hover:text-white transition-colors"
                title="Download .md"
              >
                <Download size={16} /> Markdown
              </button>
              <button
                onClick={handleDownloadPdf}
                disabled={pdfLoading}
                    aria-busy={pdfLoading}
                    aria-label={pdfLoading ? 'Preparing PDF' : 'Download PDF'}
                className="p-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                title="Download PDF"
              >
                {pdfLoading ? <Loader2 size={16} className="animate-spin" /> : <FileDown size={16} />} PDF
              </button>
              <button
                onClick={openNotionModal}
                className="p-2 text-gray-400 hover:text-indigo-300 transition-colors"
                title="Send to Notion"
              >
                <ExternalLink size={16} /> Notion
              </button>
                </div>
              </details>
            </>
          )}
          <button
            onClick={handleResummarize}
            disabled={resummarizing || !transcript}
            className="flex items-center gap-2 px-3 py-2 reader-regenerate bg-dark-surface border border-dark-border hover:bg-dark-hover disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-sm transition-colors text-white"
            title="Regenerate summary using existing transcript"
          >
            <RefreshCw size={16} className={resummarizing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">{resummarizing ? 'Regenerating…' : 'Regenerate'}</span>
          </button>
          <a
            aria-label="Open summary as HTML"
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
      
      <ReaderControls>{activeTab === 'summary' && summary && <label className="reader-contents block text-sm">Contents<select aria-label="Summary contents" className="ml-2 max-w-full bg-dark-surface border border-dark-border rounded-lg p-2" value={activeSection} onChange={e => { const id=e.target.value;const index=Number(id.replace('summary-topic-',''));if(id.startsWith('summary-topic-')&&topicEntries[index])setExpandedTopics(previous=>new Set([...previous,topicEntries[index][0]]));setActiveSection(id);requestAnimationFrame(()=>document.getElementById(id)?.scrollIntoView({block:'start'})) }}><option value="">Jump to section…</option><option value="summary-overview">Overview</option><option value="summary-key-points">Key points</option>{topicEntries.map(([topic],index)=><option key={topic} value={`summary-topic-${index}`}>{topic}</option>)}<option value="summary-takeaways">Takeaways</option></select></label>}</ReaderControls>
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
      {activeTab === 'transcript' && transcriptLoading && <div role="status" className="flex justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-500" aria-label="Loading transcript" />
      </div>}
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
          <div className="reader-section">
            <h2 id="summary-overview" className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="text-indigo-500" size={20} />
              Overview
            </h2>
            <SummaryText>{summary.overview}</SummaryText>
          </div>
          
          {/* Topics/Key Points */}
          <section className="space-y-4">
            <h2 id="summary-key-points" className="text-lg font-semibold text-white flex items-center gap-2">
              <MessageSquare className="text-indigo-400" size={20} />
              Key Points by Topic
            </h2>
            
            <div className="flex gap-3 text-sm"><button onClick={()=>setExpandedTopics(new Set(topicEntries.map(([topic])=>topic)))}>Expand all</button><button onClick={()=>setExpandedTopics(new Set())}>Collapse all</button></div>
            <div className="space-y-3" data-topic-column>
            {topicEntries.map(([topic, points], index) => (
              <div
                key={topic} data-topic-card id={`summary-topic-${index}`} aria-current={activeSection === `summary-topic-${index}` ? 'location' : undefined}
                className="topic-section"
              >
                <button
                  onClick={() => toggleTopic(topic)}
                  aria-expanded={expandedTopics.has(topic)}
                  className="topic-toggle w-full flex items-center justify-between gap-3"
                >
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0 text-left">
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
                  <div className="topic-content space-y-4">
                    {points.map((kp, idx) => (
                      <div key={idx} className="space-y-3">
                        <SummaryText>{kp.summary}</SummaryText>
                        {kp.original_quote && (
                          <div className="reader-quote flex items-start gap-2">
                            <Quote className="text-gray-500 flex-shrink-0 mt-0.5" size={16} />
                            <p className="text-sm text-gray-400">
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
          </section>
          
          {/* Takeaways */}
          {summary.takeaways.length > 0 && (
            <div className="reader-section">
              <h2 id="summary-takeaways" className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <CheckCircle className="text-green-500" size={20} />
                Takeaways
              </h2>
              <ul className="space-y-3">
                {summary.takeaways.map((takeaway: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-3">
                    <CheckCircle className="text-green-500 flex-shrink-0 mt-0.5" size={16} />
                    <SummaryText>{takeaway}</SummaryText>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      
      {activeTab === 'transcript' && transcript && (
        <div className="reader-section">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <FileText className="text-blue-500" size={20} />
            Full Transcript
          </h2>
          
          {transcript.segments.length > 0 ? (
            <TranscriptSegments key={eid} segments={transcript.segments} fallback={<p className="whitespace-pre-wrap">{transcript.text}</p>} />
          ) : (
            <p className="text-gray-300 whitespace-pre-line leading-relaxed">
              {transcript.text}
            </p>
          )}
        </div>
      )}
      
      {!summary && !transcript && !error && (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <FileText className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No content available</p>
          <p className="text-gray-500">Process this episode to generate transcript and summary</p>
        </div>
      )}

      {/* Notion export modal */}
      {notionOpen && (
        <div
          role="dialog" aria-modal="true" aria-label="Export to Notion" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setNotionOpen(false) }}
        >
          <div className="bg-dark-surface border border-dark-border rounded-2xl w-full max-w-md mx-4 shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-dark-border">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <ExternalLink size={16} />
                Send to Notion
              </h2>
              <button aria-label="Close Notion export" onClick={() => setNotionOpen(false)} className="p-1 text-gray-400 hover:text-white transition-colors">
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
              <button aria-label="Close Notion export" onClick={() => setNotionOpen(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
                {notionResult?.ok ? 'Done' : hasNotionKey ? 'Cancel' : 'Close'}
              </button>
              {hasNotionKey && !notionResult?.ok && (
                <button
                  onClick={handleNotionExport}
                  disabled={!notionSelectedId || notionExporting}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
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
