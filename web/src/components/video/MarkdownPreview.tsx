import ReaderScreenshot from '../ReaderScreenshot'
import { lazy, memo, Suspense, useEffect, useState } from 'react'
import { prepareNoteMarkdown } from '../../lib/noteMarkdown'
import { rehypeNoteHeadings } from '../../lib/noteHeadingPlugin'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { PluggableList } from 'unified'
import { Play, ExternalLink, ImageIcon } from 'lucide-react'

const HighlightedCode = lazy(() => import('./HighlightedCode'))

function NoteImage({ src, alt, priority = false }: { src?: string; alt?: string; priority?: boolean }) {
  return src ? <ReaderScreenshot src={src} alt={alt} priority={priority} /> : null
}

/** The reader owns task status; saved content remains readable in every state. */
export default function MarkdownPreview({ markdown,readerTitle }: { markdown: string;readerTitle?:string }) {
  return (
          <article data-rendering="formatted" className="note-prose prose prose-invert max-w-none pb-4
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
            <NoteMarkdown markdown={markdown} readerTitle={readerTitle}/>
          </article>
  )
}

const NoteMarkdown = memo(function NoteMarkdown({ markdown,readerTitle }: { markdown: string;readerTitle?:string }) {
  const [math, setMath] = useState<{
    remark: typeof import('remark-math').default
    rehype: typeof import('rehype-katex').default
  } | null>(null)
  const hasMath = /\$\$[\s\S]+?\$\$|(^|[^\\])\$[^\n$]+\$/.test(markdown)
  useEffect(() => {
    if (!hasMath || math) return
    let active = true
    void Promise.all([import('remark-math'), import('rehype-katex'), import('katex/dist/katex.min.css')])
      .then(([remark, rehype]) => { if (active) setMath({ remark: remark.default, rehype: rehype.default }) })
      .catch(() => {})
    return () => { active = false }
  }, [hasMath, math])
  const priorityImages = Array.from(markdown.matchAll(/!\[[^\]]*\]\(([^\s)]+)/g)).slice(0, 2).map(match => match[1])
  const rehypePlugins: PluggableList = [[rehypeNoteHeadings,{readerTitle}]]
  if (math) rehypePlugins.push([math.rehype, { throwOnError: false, errorColor: '#94a3b8' }])
  return (
            <ReactMarkdown
              remarkPlugins={math ? [remarkGfm, math.remark] : [remarkGfm]}
              rehypePlugins={rehypePlugins}
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
                      <Suspense fallback={<code className={className}>{codeStr}</code>}>
                        <HighlightedCode language={match[1]}>{codeStr}</HighlightedCode>
                      </Suspense>
                    )
                  }
                  return (
                    <code className={className} {...props}>
                      {children}
                    </code>
                  )
                },
                img({ src, alt }) {
                  return <NoteImage key={src} src={src} alt={alt} priority={!!src && priorityImages.includes(src)} />
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
                          try {
                            const el = document.getElementById(decodeURIComponent(href.slice(1)))
                            if (!el) return
                            e.preventDefault()
                            el.scrollIntoView({ block: 'start' })
                          } catch { /* Invalid source anchors remain ordinary links. */ }
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
              {prepareNoteMarkdown(markdown)}
            </ReactMarkdown>
  )
})
