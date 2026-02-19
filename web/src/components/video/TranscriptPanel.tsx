interface Segment {
  start: number
  end: number
  text: string
}

interface Props {
  transcript: {
    text: string
    segments: Segment[]
    duration: number
  } | null
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

export default function TranscriptPanel({ transcript }: Props) {
  if (!transcript) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <p>No transcript available</p>
      </div>
    )
  }

  const segments = transcript.segments || []
  const duration = transcript.duration || 0

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Transcript
        </h3>
        <span className="text-xs text-gray-500">
          {segments.length} segments
          {duration > 0 && ` | ${formatTime(duration)}`}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-1">
        {segments.length > 0 ? (
          segments.map((seg, idx) => (
            <div
              key={idx}
              className="flex gap-2 py-1.5 px-2 rounded hover:bg-dark-hover transition-colors group"
            >
              <span className="text-xs text-indigo-400 font-mono flex-shrink-0 mt-0.5 min-w-[40px]">
                {formatTime(seg.start)}
              </span>
              <p className="text-sm text-gray-300 leading-relaxed">
                {seg.text}
              </p>
            </div>
          ))
        ) : (
          <div className="p-3 text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
            {transcript.text}
          </div>
        )}
      </div>
    </div>
  )
}
