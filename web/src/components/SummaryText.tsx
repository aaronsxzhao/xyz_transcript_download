import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Safe Markdown for structured podcast summary fields. Raw HTML stays disabled. */
export default memo(function SummaryText({ children }: { children: string }) {
  return <div className="note-prose prose prose-invert max-w-none prose-p:my-2 prose-headings:mt-4 prose-headings:mb-2 prose-strong:text-white prose-a:text-indigo-300 prose-table:block prose-table:overflow-x-auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{children}</ReactMarkdown></div>
})
