import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  AlertCircle, Loader2, RotateCcw, Square,
  Play, ExternalLink, X, ImageIcon, FileText,
} from 'lucide-react'
import StepBar from './StepBar'
import YouTubeCookieGuide from './YouTubeCookieGuide'
import type { VideoTask } from '../../lib/api'

interface Props {
  task: VideoTask | null
}

export default function MarkdownPreview({ task }: Props) {
  const [zoomedImg, setZoomedImg] = useState<string | null>(null)
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

  return (
    <div>

      {/* Progress bar for active tasks */}
      {isActive && (
        <div className="mb-4 flex-shrink-0">
          <StepBar currentStatus={task.status} progress={task.progress} />
          <div className="flex items-center justify-center gap-3 mt-3">
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
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Loader2 size={32} className="animate-spin mb-3 text-indigo-400" />
          <p>Queued for processing...</p>
        </div>
      )}

      {/* Failed state */}
      {isFailed && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
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
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
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
        <div>
          {isActive && (
            <div className="flex items-center gap-2 mb-3 px-1 text-xs text-indigo-400">
              <Loader2 size={12} className="animate-spin" />
              <span>Writing notes...</span>
            </div>
          )}
          <article className="prose prose-invert max-w-none pb-4
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
              rehypePlugins={[rehypeSlug, [rehypeKatex, { throwOnError: false, errorColor: '#94a3b8' }]]}
              components={{
                p({ children, ...props }) {
                  const childArray = Array.isArray(children) ? children : [children]
                  const processed = childArray.map((child, i) => {
                    if (typeof child !== 'string') return child
                    const screenshotRegex = /\*?Screenshot-\[(\d+(?::\d+){1,2})\]\*?/g
                    const parts: React.ReactNode[] = []
                    let lastIdx = 0
                    let match
                    while ((match = screenshotRegex.exec(child)) !== null) {
                      if (match.index > lastIdx) parts.push(child.slice(lastIdx, match.index))
                      const ts = match[1]
                      parts.push(
                        <span key={`ss-${i}-${ts}`} className="inline-flex items-center gap-1.5 px-2.5 py-1 my-1 bg-slate-700/50 border border-slate-600/50 rounded-lg text-xs text-slate-400">
                          <ImageIcon size={12} />
                          Screenshot @ {ts}
                        </span>
                      )
                      lastIdx = match.index + match[0].length
                    }
                    if (parts.length === 0) return child
                    if (lastIdx < child.length) parts.push(child.slice(lastIdx))
                    return parts
                  })
                  return <p {...props}>{processed.flat()}</p>
                },
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
                      className="max-w-[min(100%,480px)] max-h-64 w-auto rounded-lg border border-dark-border cursor-pointer hover:opacity-90 transition-opacity"
                      loading="lazy"
                      referrerPolicy="no-referrer"
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
                  if (href?.startsWith('#')) {
                    return (
                      <a
                        href={href}
                        onClick={(e) => {
                          e.preventDefault()
                          const id = decodeURIComponent(href.slice(1))
                          const el = document.getElementById(id)
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
                        }}
                        className="text-indigo-400 hover:underline hover:text-indigo-300 transition-colors"
                      >
                        {children}
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
              {task.markdown
                .replace(/^##\s*(?:目录|Table of Contents)\s*\n(?:[\s\S]*?)(?=\n---\n|\n## )/m, '')
                .replace(/^\n---\n/m, '\n')
              }
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
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          {/* Circular progress */}
          <div className="relative w-16 h-16 mb-4">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 64 64">
              <circle cx="32" cy="32" r="28" fill="none" stroke="currentColor" strokeWidth="3" className="text-dark-border" />
              <circle
                cx="32" cy="32" r="28" fill="none" strokeWidth="3"
                className="text-indigo-500"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 28}`}
                strokeDashoffset={`${2 * Math.PI * 28 * (1 - task.progress / 100)}`}
                style={{ transition: 'stroke-dashoffset 1.2s ease-out' }}
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-300">
              {Math.round(task.progress)}%
            </span>
          </div>
          <p className="text-sm text-gray-400">{task.message || 'Processing...'}</p>
        </div>
      )}
    </div>
  )
}
