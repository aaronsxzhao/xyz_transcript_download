import { Link } from 'react-router-dom'
import { Tag, MessageSquare } from 'lucide-react'
import type { SummaryListItem } from '../lib/api'

interface SummaryCardProps {
  summary: SummaryListItem
}

export default function SummaryCard({ summary }: SummaryCardProps) {
  return (
    <Link
      to={`/viewer/${summary.episode_id}`}
      className="block p-4 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors"
    >
      <h3 className="font-medium text-white line-clamp-2 mb-3">
        {summary.title}
      </h3>
      
      <div className="flex items-center gap-4 text-sm text-gray-400">
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
