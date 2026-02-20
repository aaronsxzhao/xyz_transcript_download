import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  Copy, Download, Check, FileText, AlertCircle, Loader2, RotateCcw, Square,
  Play, ExternalLink, X, FileDown,
} from 'lucide-react'
import StepBar from './StepBar'
import YouTubeCookieGuide from './YouTubeCookieGuide'
import type { VideoTask } from '../../lib/api'

interface Props {
  task: VideoTask | null
}

export default function MarkdownPreview({ task }: Props) {
  const [copied, setCopied] = useState(false)
  const [zoomedImg, setZoomedImg] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const navigate = useNavigate()

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <FileText size={48} className="mb-4 opacity-30" />
        <p className="text-lg">Select a task or start a new one</p>
        <p className="text-sm mt-1">Your generated notes will appear here</p>
      </div>
    )
  }

  const isActive = !['success', 'failed', 'cancelled', 'pending'].includes(task.status) && task.status !== ''
  const isFailed = task.status === 'failed'
  const isCancelled = task.status === 'cancelled'
  const isSuccess = task.status === 'success'

  const handleCopy = async () => {
    if (!task.markdown) return
    await navigator.clipboard.writeText(task.markdown)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    if (!task.markdown) return
    const blob = new Blob([task.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${task.title || 'notes'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleDownloadPdf = async () => {
    if (!task?.markdown || pdfLoading) return
    setPdfLoading(true)
    try {
      const [html2pdfModule, markedModule] = await Promise.all([
        import('html2pdf.js'),
        import('marked'),
      ])
      const html2pdf = html2pdfModule.default
      const { marked } = markedModule

      marked.setOptions({ gfm: true, breaks: false })
      const body = await marked.parse(task.markdown)

      const wrapper = document.createElement('div')
      wrapper.innerHTML = `
        <style>
          * { box-sizing: border-box; }
          body, div { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; }
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
          table, img, blockquote, pre { page-break-inside: avoid; }
          h1, h2, h3 { page-break-after: avoid; }
        </style>
        <div style="color:#1f2937; background:#fff; padding:0; font-size:13px; line-height:1.75;">
          ${body}
        </div>
      `

      const filename = `${(task.title || 'notes').replace(/[^\w\s-]/g, '').trim()}.pdf`
      await html2pdf().set({
        margin: [12, 14, 12, 14],
        filename,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, logging: false },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
      }).from(wrapper).save()
    } catch (e) {
      console.error('PDF generation failed:', e)
    } finally {
      setPdfLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="text-sm font-semibold text-white truncate">
            {task.title || 'Generating...'}
          </h3>
          {task.style && (
            <span className="px-2 py-0.5 bg-purple-600/20 text-purple-400 text-xs rounded-full flex-shrink-0">
              {task.style}
            </span>
          )}
        </div>
        {task.markdown && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={handleCopy}
              className="p-1.5 text-gray-400 hover:text-white transition-colors"
              title="Copy to clipboard"
            >
              {copied ? <Check size={15} className="text-green-400" /> : <Copy size={15} />}
            </button>
            <button
              onClick={handleDownload}
              className="p-1.5 text-gray-400 hover:text-white transition-colors"
              title="Download Markdown"
            >
              <Download size={15} />
            </button>
            {isSuccess && (
              <button
                onClick={handleDownloadPdf}
                disabled={pdfLoading}
                className="p-1.5 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                title="Download PDF"
              >
                {pdfLoading ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Progress bar for active tasks */}
      {isActive && (
        <div className="mb-4 flex-shrink-0">
          <StepBar currentStatus={task.status} />
          <div className="mt-3 h-1.5 bg-dark-border rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full"
              style={{ width: `${task.progress}%`, transition: 'width 1.2s ease-out' }}
            />
          </div>
          <div className="flex items-center justify-center gap-3 mt-2">
            <p className="text-xs text-gray-500">
              {task.message || 'Processing...'}
            </p>
            <button
              onClick={async () => {
                try {
                  const { cancelVideoTask } = await import('../../lib/api')
                  await cancelVideoTask(task.id)
                } catch (e) {
                  console.error('Cancel failed:', e)
                }
              }}
              className="flex items-center gap-1 px-2 py-0.5 text-xs text-orange-400 hover:text-orange-300 border border-orange-500/30 hover:border-orange-400/50 rounded transition-colors"
            >
              <Square size={10} className="fill-current" />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Pending state */}
      {task.status === 'pending' && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
          <Loader2 size={32} className="animate-spin mb-3 text-indigo-400" />
          <p>Queued for processing...</p>
        </div>
      )}

      {/* Failed state */}
      {isFailed && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
          <AlertCircle size={32} className="mb-3 text-red-400" />
          <p className="text-red-400">Processing failed</p>
          {(() => {
            const isYouTubeLogin = (task.error === 'LOGIN_REQUIRED' || task.error === 'AGE_RESTRICTED' || task.error === 'COOKIES_REQUIRED')
              && task.platform === 'youtube'
            const needsSettings = [
              'BILIBILI_LOGIN_REQUIRED', 'LOGIN_REQUIRED', 'COOKIES_REQUIRED', 'AGE_RESTRICTED',
            ].includes(task.error || '') && !isYouTubeLogin
            const errorMessages: Record<string, string> = {
              BILIBILI_LOGIN_REQUIRED: 'BiliBili requires login. Please scan the QR code in Settings → BiliBili Login.',
              LOGIN_REQUIRED: 'This video requires login.',
              COOKIES_REQUIRED: 'Server rejected the request.',
              AGE_RESTRICTED: 'This video is age-restricted and requires login.',
              VIDEO_PRIVATE: 'This video is private and cannot be accessed.',
              VIDEO_UNAVAILABLE: 'This video has been removed or is no longer available.',
              GEO_RESTRICTED: 'This video is not available in your region.',
              COPYRIGHT_BLOCKED: 'This video is blocked due to copyright restrictions.',
              RATE_LIMITED: 'Rate limited by the platform. Please wait a few minutes and try again.',
              FFMPEG_MISSING: 'FFmpeg is required but not installed on the server.',
              UNSUPPORTED_URL: 'This URL is not supported. Please check the URL and try again.',
            }
            const displayMsg = errorMessages[task.error || ''] || task.message || task.error || 'Unknown error'

            return (
              <>
                <p className="text-sm mt-2 text-center text-gray-400 max-w-md">
                  {displayMsg}
                </p>

                {isYouTubeLogin && (
                  <div className="mt-4 p-4 bg-dark-hover rounded-xl border border-dark-border max-w-md w-full">
                    <YouTubeCookieGuide compact />
                  </div>
                )}

                <div className="flex items-center gap-3 mt-4">
                  {(needsSettings || isYouTubeLogin) && (
                    <button
                      onClick={() => navigate('/settings')}
                      className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white text-sm rounded-lg transition-colors"
                    >
                      {isYouTubeLogin ? 'Upload Cookies in Settings' : 'Go to Settings'}
                    </button>
                  )}
                  <button
                    onClick={async () => {
                      try {
                        const { retryVideoTask } = await import('../../lib/api')
                        await retryVideoTask(task.id)
                      } catch (e) {
                        console.error('Retry failed:', e)
                      }
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition-colors"
                  >
                    <RotateCcw size={14} />
                    Retry
                  </button>
                </div>
              </>
            )
          })()}
        </div>
      )}

      {/* Cancelled state */}
      {isCancelled && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
          <Square size={32} className="mb-3 text-orange-400" />
          <p className="text-orange-400">Processing cancelled</p>
          <button
            onClick={async () => {
              try {
                const { retryVideoTask } = await import('../../lib/api')
                await retryVideoTask(task.id)
              } catch (e) {
                console.error('Retry failed:', e)
              }
            }}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition-colors"
          >
            <RotateCcw size={14} />
            Retry
          </button>
        </div>
      )}

      {/* Markdown content (finished or streaming) */}
      {(isSuccess || (isActive && task.markdown)) && task.markdown && (
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {isActive && (
            <div className="flex items-center gap-2 mb-3 px-1 text-xs text-indigo-400">
              <Loader2 size={12} className="animate-spin" />
              <span>Writing notes...</span>
            </div>
          )}
          <article className="prose prose-invert max-w-none
            prose-headings:text-gray-100 prose-headings:font-bold
            prose-h1:text-2xl prose-h1:border-b prose-h1:border-dark-border prose-h1:pb-2 prose-h1:mb-6
            prose-h2:text-xl prose-h2:mt-8 prose-h2:mb-4 prose-h2:text-indigo-300
            prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
            prose-p:text-gray-300 prose-p:leading-7
            prose-li:text-gray-300
            prose-strong:text-white
            prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline
            prose-blockquote:border-l-indigo-500 prose-blockquote:bg-indigo-950/30 prose-blockquote:text-gray-300 prose-blockquote:py-1 prose-blockquote:rounded-r
            prose-code:text-indigo-300 prose-code:bg-dark-hover prose-code:px-1 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-transparent prose-pre:p-0
            prose-img:rounded-lg prose-img:border prose-img:border-dark-border
            prose-hr:border-dark-border prose-hr:my-8
            prose-table:border-collapse prose-th:bg-dark-hover prose-th:border prose-th:border-dark-border prose-th:px-3 prose-th:py-2
            prose-td:border prose-td:border-dark-border prose-td:px-3 prose-td:py-2
          ">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '')
                  const codeStr = String(children).replace(/\n$/, '')
                  if (match) {
                    return (
                      <SyntaxHighlighter
                        style={vscDarkPlus}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          borderRadius: '0.5rem',
                          fontSize: '0.8125rem',
                        }}
                      >
                        {codeStr}
                      </SyntaxHighlighter>
                    )
                  }
                  return (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  )
                },
                img({ src, alt }) {
                  return (
                    <img
                      src={src}
                      alt={alt || ''}
                      className="max-w-full rounded-lg border border-dark-border cursor-pointer hover:opacity-90 transition-opacity"
                      loading="lazy"
                      onClick={() => src && setZoomedImg(src)}
                    />
                  )
                },
                a({ href, children }) {
                  const text = String(children)
                  const isTimestamp = /^▶/.test(text) || /原片/.test(text)
                  if (isTimestamp && href) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/20 border border-indigo-500/30 rounded-full text-xs text-indigo-300 hover:bg-indigo-600/40 hover:text-indigo-200 transition-colors no-underline"
                      >
                        <Play size={10} className="fill-current" />
                        {text.replace(/^▶\s*/, '')}
                      </a>
                    )
                  }
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-400 hover:underline inline-flex items-center gap-0.5"
                    >
                      {children}
                      <ExternalLink size={11} className="opacity-50" />
                    </a>
                  )
                },
              }}
            >
              {task.markdown}
            </ReactMarkdown>
          </article>
        </div>
      )}

      {/* Image zoom overlay */}
      {zoomedImg && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center cursor-zoom-out"
          onClick={() => setZoomedImg(null)}
        >
          <button
            onClick={() => setZoomedImg(null)}
            className="absolute top-4 right-4 text-white/70 hover:text-white p-2"
          >
            <X size={24} />
          </button>
          <img
            src={zoomedImg}
            alt="Zoomed screenshot"
            className="max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl"
          />
        </div>
      )}

      {/* Loading state for active but no markdown yet */}
      {isActive && !task.markdown && task.status !== 'pending' && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
          <Loader2 size={32} className="animate-spin mb-3 text-indigo-400" />
          <p className="text-sm">{task.message || 'Processing...'}</p>
        </div>
      )}
    </div>
  )
}
