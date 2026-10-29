import {useNavigate} from 'react-router-dom'
import type {VideoTask} from '../../lib/api'

export default function BilibiliParts({metadata}: {metadata:NonNullable<VideoTask['source_metadata']>}) {
  const navigate=useNavigate()
  const parts=metadata.bilibili_parts || []
  if(parts.length<2) return null
  return <nav aria-label="Bilibili collection parts" className="mb-4 text-sm text-gray-400">
    <p className="mb-2">Part {metadata.bilibili_part?.page} of {parts.length} · Each part has its own summary and processing status.</p>
    <label className="flex flex-wrap items-center gap-2">Browse parts
      <select className="min-w-0 max-w-full rounded-lg bg-gray-800 p-2" value={metadata.bilibili_part?.page}
        onChange={event => {
          const part=parts.find(item=>item.page===Number(event.target.value))
          if(part?.task_id) navigate(`/videos/${part.task_id}`)
          else if(part) window.open(part.url,'_blank','noopener,noreferrer')
        }}>
        {parts.map(part=><option key={part.page} value={part.page}>{part.title}{!part.task_id?' · Original source':''}</option>)}
      </select>
    </label>
  </nav>
}
