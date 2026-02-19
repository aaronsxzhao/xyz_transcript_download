import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  Copy, Download, Check, FileText, AlertCircle, Loader2, RotateCcw,
} from 'lucide-react'
import StepBar from './StepBar'
import type { VideoTask } from '../../lib/api'

interface Props {
  task: VideoTask | null
}

export default function MarkdownPreview({ task }: Props) {
  const [copied, setCopied] = useState(false)

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <FileText size={48} className="mb-4 opacity-30" />
        <p className="text-lg">Select a task or start a new one</p>
        <p className="text-sm mt-1">Your generated notes will appear here</p>
      </div>
    )
  }

  const isActive = !['success', 'failed', 'pending'].includes(task.status) && task.status !== ''
  const isFailed = task.status === 'failed'
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
          <p className="text-xs text-gray-500 mt-1.5 text-center">
            {task.message || 'Processing...'}
          </p>
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
          <p className="text-sm mt-1">{task.error || task.message}</p>
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
          <article className="prose prose-invert prose-sm max-w-none
            prose-headings:text-gray-100 prose-p:text-gray-300 prose-li:text-gray-300
            prose-strong:text-white prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline
            prose-blockquote:border-l-indigo-500 prose-blockquote:text-gray-400
            prose-code:text-indigo-300 prose-code:bg-dark-hover prose-code:px-1 prose-code:py-0.5 prose-code:rounded
            prose-pre:bg-transparent prose-pre:p-0
            prose-img:rounded-lg prose-img:border prose-img:border-dark-border
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
