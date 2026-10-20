import { memo } from 'react'
import ReadableMarkdown from './ReadableMarkdown'

export default memo(function SummaryText({children}:{children:string}) {
  return <div className="note-prose prose prose-invert max-w-none prose-p:my-2 prose-headings:mt-4 prose-headings:mb-2 prose-strong:text-white prose-a:text-indigo-300"><ReadableMarkdown markdown={children}/></div>
})
