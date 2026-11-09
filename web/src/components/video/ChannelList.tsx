import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Video, ExternalLink, RefreshCw, Trash2 } from 'lucide-react'
import CachedImage from '../CachedImage'
import type { VideoChannelStat } from '../../lib/api'
import { UNKNOWN_CHANNEL, channelLabel } from '../../lib/videoChannels'

export default function ChannelList({ channels, onSelectChannel, onDeleteChannel, onCheckUpdates, checkingUpdates = false }: {
  channels: VideoChannelStat[]
  onSelectChannel: (ch: string) => void
  onDeleteChannel?: (ch: string) => Promise<void> | void
  onCheckUpdates?: (ch: string) => Promise<void>
  checkingUpdates?: boolean
}) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [refreshing, setRefreshing] = useState<string | null>(null)

  if (channels.length === 0) {
    return (
      <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
        <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <p className="text-xl text-gray-400 mb-2">No channels found</p>
        <p className="text-gray-500">Process some videos to see channels here</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {channels.map((ch,index) => {
        const imgSrc = ch.channel_avatar || ch.thumbnail
        return (
          <div
            key={ch.channel}
            className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
          >
            <div className="collection-row">
              <Link className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0" to={'/videos?'+new URLSearchParams({platform:ch.platform,channel:ch.channel})}>
                {imgSrc ? (
                  <CachedImage priority={index<3} src={imgSrc} alt="" className={`w-14 h-14 md:w-20 md:h-20 flex-shrink-0 bg-dark-hover object-cover ${ch.channel_avatar ? 'rounded-full' : 'rounded-lg'}`} />
                ) : (
                  <div className="w-14 h-14 md:w-20 md:h-20 rounded-full bg-dark-hover flex items-center justify-center flex-shrink-0">
                    <Video className="w-6 h-6 md:w-8 md:h-8 text-gray-600" />
                  </div>
                )}

                <div className="flex-1 min-w-0">
                  <h3 className="text-base md:text-lg font-semibold text-white mb-1 line-clamp-2">
                    {channelLabel(ch.channel)}
                  </h3>
                  <p className="text-sm text-indigo-400 mt-1 md:mt-2">
                    {ch.done > 0
                      ? `${ch.done} / ${ch.total} completed`
                      : `${ch.total} video${ch.total !== 1 ? 's' : ''}`
                    }
                  </p>
                </div>
              </Link>

              <div className="channel-actions collection-actions">
                <button
                  onClick={() => onSelectChannel(ch.channel)}
                  aria-label={`Open videos from ${channelLabel(ch.channel)}`}
                  className="ui-button ui-button-icon-mobile"
                >
                  <Video size={16} />
                  <span className="hidden sm:inline">Videos</span>
                </button>
                {ch.channel_url && (
                  <a
                    href={ch.channel_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ui-button ui-button-icon"
                    title="Open channel page"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
                {onCheckUpdates && ch.channel_url && (
                  <button
                    onClick={async () => {
                      setRefreshing(ch.channel)
                      try { await onCheckUpdates(ch.channel) } finally { setRefreshing(null) }
                    }}
                    disabled={checkingUpdates || refreshing !== null} aria-busy={refreshing === ch.channel}
                    className="ui-button ui-button-icon disabled:opacity-50"
                    title="Check for new content"
                    aria-label={`Check updates for ${channelLabel(ch.channel)}`}
                  >
                    <RefreshCw size={16} className={refreshing === ch.channel ? 'animate-spin' : ''} />
                  </button>
                )}
                {onDeleteChannel && ch.channel !== UNKNOWN_CHANNEL && (
                  confirmDelete === ch.channel ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={async () => {
                          setDeleting(true)
                          try { await onDeleteChannel(ch.channel) } finally { setDeleting(false); setConfirmDelete(null) }
                        }}
                        disabled={deleting} aria-busy={deleting}
                        className="ui-button ui-button-danger"
                      >
                        {deleting ? 'Deleting...' : 'Confirm'}
                      </button>
                      <button
                        disabled={deleting}
                        onClick={() => setConfirmDelete(null)}
                        className="ui-button"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      disabled={deleting}
                      onClick={() => setConfirmDelete(ch.channel)}
                      className="ui-button ui-button-icon ui-button-danger"
                      title="Delete channel and all its videos"
                    >
                      <Trash2 size={16} />
                    </button>
                  )
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
