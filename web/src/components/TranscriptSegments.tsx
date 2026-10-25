import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

interface Segment { start: number; end: number; text: string }

export default function TranscriptSegments({segments,text=''}:{segments:Segment[];text?:string}) {
  const [fullText,setFullText]=useState(false)
  const hasText=!!text.trim()
  return <>
    {hasText&&segments.length>0&&<div role="group" aria-label="Transcript view" className="reader-segments flex-wrap mb-3 w-fit max-w-full">
      <button type="button" className="reader-action" aria-pressed={!fullText} onClick={()=>setFullText(false)}>Timed segments</button>
      <button type="button" className="reader-action" aria-pressed={fullText} onClick={()=>setFullText(true)}>Full text</button>
    </div>}
    {(fullText&&hasText)||!segments.length?<div role="region" aria-label="Full transcript text" tabIndex={0} className="overflow-y-auto custom-scrollbar" style={{maxHeight:'min(60vh, 600px)'}}><p className="text-sm text-gray-300 leading-7 whitespace-pre-wrap break-words">{text||'No transcript available'}</p></div>:<TimedSegments segments={segments}/>}
  </>
}

function TimedSegments({ segments }: { segments: Segment[] }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 64,
    overscan: 8,
  })

  return <div ref={scrollRef} role="region" aria-label="Transcript segments" tabIndex={0}
    className="overflow-y-auto custom-scrollbar" style={{ height: 'min(60vh, 600px)', overflowAnchor: 'none' }}>
    <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
      {virtualizer.getVirtualItems().map(row => {
        const segment = segments[row.index]
        const minutes = Math.floor(segment.start / 60)
        const seconds = Math.floor(segment.start % 60).toString().padStart(2, '0')
        return <div key={row.key} data-index={row.index} ref={virtualizer.measureElement}
          className="absolute top-0 left-0 w-full flex gap-3 py-2 px-2 rounded hover:bg-dark-hover"
          style={{ transform: `translateY(${row.start}px)` }}>
          <span className="text-xs text-indigo-400 font-mono shrink-0 pt-1 min-w-[44px]">{minutes}:{seconds}</span>
          <p className="text-sm text-gray-300 leading-7 min-w-0 break-words">{segment.text}</p>
        </div>
      })}
    </div>
  </div>
}
