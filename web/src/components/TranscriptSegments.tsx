import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'

interface Segment { start: number; end: number; text: string }

export default function TranscriptSegments({ segments }: { segments: Segment[] }) {
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
