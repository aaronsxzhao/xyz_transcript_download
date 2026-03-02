import { Link } from 'react-router-dom'
import { Tag, MessageSquare, Radio } from 'lucide-react'
import type { SummaryListItem } from '../lib/api'

interface SummaryCardProps {
  summary: SummaryListItem
}

export default function SummaryCard({ summary }: SummaryCardProps) {
  return (
    <Link
      to={`/viewer/${summary.episode_id}`}
      className="flex flex-col justify-between p-4 min-h-[104px] bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors"
    >
      <h3 className="font-medium text-white line-clamp-2">
        {summary.title}
      </h3>
      
      <div className="flex items-center gap-4 text-sm text-gray-400 mt-auto">
        {summary.podcast_title && (
          <span className="flex items-center gap-1.5 truncate">
            {summary.podcast_cover ? (
              <img
                src={summary.podcast_cover}
                alt=""
                className="w-4 h-4 rounded-full flex-shrink-0 bg-dark-hover"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                referrerPolicy="no-referrer"
              />
            ) : (
              <Radio size={14} className="text-indigo-400 flex-shrink-0" />
            )}
            <span className="truncate">{summary.podcast_title}</span>
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <Tag size={14} />
          <span>{summary.topics_count} topics</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MessageSquare size={14} />
          <span>{summary.key_points_count} points</span>
        </div>
      </div>
    </Link>
  )
}
