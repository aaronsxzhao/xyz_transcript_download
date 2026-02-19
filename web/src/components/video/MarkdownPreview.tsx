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
} from 'lucide-react'
import StepBar from './StepBar'
import type { VideoTask } from '../../lib/api'

interface Props {
  task: VideoTask | null
}

export default function MarkdownPreview({ task }: Props) {
  const [copied, setCopied] = useState(false)
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
        {isSuccess && task.markdown && (
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
              title="Download .md"
            >
              <Download size={15} />
            </button>
          </div>
        )}
      </div>

      {/* Progress bar for active tasks */}
      {isActive && (
        <div className="mb-4 flex-shrink-0">
          <StepBar currentStatus={task.status} />
          <div className="mt-3 h-1.5 bg-dark-border rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all duration-500 rounded-full"
              style={{ width: `${task.progress}%` }}
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
            const needsSettings = [
              'BILIBILI_LOGIN_REQUIRED', 'LOGIN_REQUIRED', 'COOKIES_REQUIRED', 'AGE_RESTRICTED',
            ].includes(task.error || '')
            const errorMessages: Record<string, string> = {
              BILIBILI_LOGIN_REQUIRED: 'BiliBili requires login. Please scan the QR code in Settings → BiliBili Login.',
              LOGIN_REQUIRED: 'This video requires login. Please set cookies in Settings → Platform Cookies.',
              COOKIES_REQUIRED: 'Server rejected the request. Please set cookies in Settings → Platform Cookies.',
              AGE_RESTRICTED: 'This video is age-restricted. Please set cookies from a logged-in browser in Settings.',
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
                <div className="flex items-center gap-3 mt-4">
                  {needsSettings && (
                    <button
                      onClick={() => navigate('/settings')}
                      className="flex items-center gap-2 px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white text-sm rounded-lg transition-colors"
                    >
                      Go to Settings
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

      {/* Markdown content */}
      {isSuccess && task.markdown && (
        <div className="flex-1 overflow-y-auto custom-scrollbar">
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
                    />
                  )
                },
              }}
            >
              {task.markdown}
            </ReactMarkdown>
          </article>
        </div>
      )}

      {/* Loading state for active but no markdown yet */}
      {isActive && !task.markdown && task.status !== 'pending' && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-500">
          <Loader2 size={32} className="animate-spin mb-3 text-indigo-400" />
          <p>{task.message || 'Processing...'}</p>
        </div>
      )}
    </div>
  )
}
