import { memo } from 'react'
import ReadableMarkdown from './ReadableMarkdown'
import { normalizeSummaryMarkdown } from '../lib/summaryReading'

export default memo(function SummaryText({children}:{children:string}) {
  return <div className="note-prose prose prose-invert max-w-none prose-strong:text-white prose-a:text-indigo-300"><ReadableMarkdown markdown={normalizeSummaryMarkdown(children)}/></div>
})
