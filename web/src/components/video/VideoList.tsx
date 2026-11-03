import '../SeriesCard.css'
import {useRef,useState} from 'react'
import {Link,useNavigate} from 'react-router-dom'
import {CheckCircle,XCircle,Video,ChevronDown,Square,Sparkles,Play,RotateCcw,ExternalLink,RefreshCw} from 'lucide-react'
import {groupVideoCollections,partLabel,collectionIdentity} from '../../lib/bilibiliCollection'
import ItemActions,{useItemActionList} from '../ItemActions'
import {videoFailureHint} from '../../lib/videoFailure'
import {sourceAction,TaskProgress} from '../TaskStatus'
import ContentDates from '../ContentDates'
import CachedImage from '../CachedImage'
import {prefetchVideoNote} from '../../lib/summaryPrefetch'
import {isNewItem} from '../../lib/seen'
import type {VideoTask} from '../../lib/api'

function getDisplayTitle(task: VideoTask): string {
  if (task.title && task.title !== 'Untitled') return task.title
  if (task.url) {
    if (task.platform === 'local') {
      const parts = task.url.split(/[\/\\]/)
      const filename = parts[parts.length - 1] || task.url
      return filename.replace(/\.[^.]+$/, '') || filename
    }
    try {
      const u = new URL(task.url)
      const host = u.hostname.replace('www.', '')
      const path = u.pathname.replace(/\/$/, '')
      const shortPath = path.length > 40 ? '...' + path.slice(-37) : path
      return `${host}${shortPath}`
    } catch {
      return task.url.length > 60 ? task.url.slice(0, 57) + '...' : task.url
    }
  }
  return 'Untitled'
}


export default function VideoList({ videos, onDelete, onRetry, onCancel }: {
  videos: VideoTask[]
  onDelete: (id: string, summaryOnly?:boolean) => Promise<void>
  onRetry: (id: string) => Promise<void>
  onCancel: (id: string) => Promise<void>
}) {
  const navigate = useNavigate()
  const list=useItemActionList()
  const activeActions = useRef(new Set<string>())
  const [pending, setPending] = useState(new Set<string>())
  const runAction = async (id:string, action:(id:string)=>Promise<void>) => {
    if (activeActions.current.has(id)) return
    activeActions.current.add(id); setPending(new Set(activeActions.current))
    try { await action(id) } finally { activeActions.current.delete(id); setPending(new Set(activeActions.current)) }
  }
  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60)
    return `${m} min`
  }

  const isProcessing = (status: string) =>
    !['success', 'failed', 'cancelled', 'discovered'].includes(status)

  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())
  const toggleError = (id: string) => {
    setExpandedErrors(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  if (videos.length === 0) {
    return (
      <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
        <Video className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <p className="text-xl text-gray-400 mb-2">No videos in this channel</p>
        <p className="text-gray-500">Process some videos to see them here</p>
      </div>
    )
  }

  const renderTask = (task:VideoTask,index:number) => {
        const isFailed = task.status === 'failed'
        const errorMsg = task.message && task.message !== 'Failed' ? task.message : task.error || ''
        const hint = isFailed ? videoFailureHint(task) : null
        const identity = collectionIdentity(task)
        const displayTitle = identity && identity.total > 1 ? `P${identity.page} · ${partLabel(getDisplayTitle(task))}` : getDisplayTitle(task)

        const isClickable = task.status === 'success'
        return (
        <div
          key={task.id}
          onClick={isClickable ? () => navigate(`/videos/${task.id}`) : undefined}
          onPointerEnter={isClickable ? () => prefetchVideoNote(task.id) : undefined}
          onTouchStart={isClickable ? () => prefetchVideoNote(task.id) : undefined}
          className={`p-3 md:p-4 bg-dark-surface border rounded-xl transition-colors ${
            isFailed ? 'border-red-500/30 hover:border-red-500/50' : 'border-dark-border hover:border-dark-hover'
          } ${isClickable ? 'cursor-pointer' : ''}`}
        >
          <div className="video-task-content flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
            {task.thumbnail ? (
              <CachedImage priority={index<3} src={task.thumbnail} alt="" fit="contain" className="video-thumbnail w-full sm:w-40 md:w-48 h-24 sm:h-24 md:h-28 rounded-lg object-cover flex-shrink-0 bg-dark-hover" />
            ) : (
              <div className={`video-thumbnail hidden sm:flex w-40 md:w-48 h-24 md:h-28 rounded-lg items-center justify-center flex-shrink-0 ${
                isFailed ? 'bg-red-500/10' : 'bg-dark-hover'
              }`}>
                {isFailed ? (
                  <XCircle className="w-8 h-8 text-red-500/50" />
                ) : (
                  <Video className="w-8 h-8 text-gray-600" />
                )}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-white mb-1 line-clamp-2 text-sm md:text-base">
                {displayTitle}
              </h3>

              {(!task.title || task.title === 'Untitled') && task.url && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 mb-1 truncate"
                >
                  <ExternalLink size={10} className="flex-shrink-0" />
                  <span className="truncate">{task.url}</span>
                </a>
              )}

              <div className="flex flex-wrap items-center gap-2 md:gap-4 text-xs md:text-sm text-gray-400">
                <ContentDates published={task.published_at} imported={task.created_at} local={task.platform === "local"} compact />
                {task.duration > 0 && (
                  <span>{formatDuration(task.duration)}</span>
                )}

                {task.status === 'success' && (
                  <span className="flex items-center gap-1 text-green-500">
                    <CheckCircle size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Completed</span>
                  </span>
                )}
                {task.status === 'failed' && (
                  <button
                    onClick={() => toggleError(task.id)}
                    className="flex items-center gap-1 text-red-300 hover:text-red-200 transition-colors"
                  >
                    <XCircle size={12} className="md:w-3.5 md:h-3.5" />
                    Failed
                    <ChevronDown size={12} className={`transition-transform ${expandedErrors.has(task.id) ? 'rotate-180' : ''}`} />
                  </button>
                )}
                {task.status === 'cancelled' && (
                  <span className="flex items-center gap-1 text-orange-400">
                    <Square size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Cancelled</span>
                  </span>
                )}
                {['discovered', 'pending'].includes(task.status) && isNewItem(task.id) && (
                  <span className="flex items-center gap-1 text-cyan-400">
                    <Sparkles size={12} className="md:w-3.5 md:h-3.5" />
                    <span className="hidden sm:inline">Newly Added</span>
                  </span>
                )}
              </div>

              {isFailed && errorMsg && (
                <div className="mt-2">
                  <p className={`text-xs text-red-300 ${expandedErrors.has(task.id) ? '' : 'line-clamp-1'}`}>
                    {errorMsg}
                  </p>
                  {hint && (
                    <p className="mt-1.5 text-xs text-amber-400/80 flex items-start gap-1.5">
                      <span className="flex-shrink-0 mt-0.5">💡</span>
                      <span>{hint}</span>
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="collection-actions" onClick={e => e.stopPropagation()}>
              {pending.has(task.id) && <span role="status" className="text-xs text-indigo-300">Submitting…</span>}
              {(() => {
                if (task.status === 'success') {
                  return (
                    <>
                      <Link
                        to={`/videos/${task.id}`}
                        onFocus={() => prefetchVideoNote(task.id)}
                        className="ui-button ui-button-primary"
                      >
                        <CheckCircle size={16} />
                        View
                      </Link>
                    </>
                  )
                }

                if (task.status === 'discovered') {
                  return (
                    <button
                      disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                      className="ui-button"
                      title="Start processing this video"
                    >
                      <Play size={16} />
                      Process
                    </button>
                  )
                }

                if (isProcessing(task.status)) {
                  return <div className="collection-task"><TaskProgress status={task.status} progress={task.progress} startedAt={task.started_at} message={task.message} compact/></div>
                }

                if(sourceAction(errorMsg))return <Link className="ui-button" to="/settings">Check source access</Link>
                return (
                  <button
                    disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                    className="ui-button"
                  >
                    <RotateCcw size={16} />
                    Retry
                  </button>
                )
              })()}

              {task.url && task.platform !== 'local' && !isProcessing(task.status) && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ui-button ui-button-icon"
                  title="Open original source" aria-label={`Open original source for ${displayTitle}`}
                >
                  <ExternalLink size={16} />
                </a>
              )}

              <ItemActions title={displayTitle} kind="video" busy={pending.has(task.id)}
                hasSummary={task.status!=='discovered' && !isProcessing(task.status)}
                onDeleteSummary={()=>void runAction(task.id,id=>onDelete(id,true))} onDeleteItem={()=>void runAction(task.id,onDelete)}>
                    {task.status === 'success' && (
                      <button
                        disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onRetry)}
                        className="ui-button"
                        title="Re-process video" aria-label={`Re-process ${displayTitle}`}
                      >
                        <RefreshCw size={16} /><span>Re-Process</span>
                      </button>
                    )}
              </ItemActions>

              {isProcessing(task.status) && task.status !== 'cancelling' && (
                <button
                  disabled={pending.has(task.id)} aria-busy={pending.has(task.id)} onClick={() => void runAction(task.id, onCancel)}
                  className="ui-button ui-button-icon"
                  title="Cancel processing"
                >
                  <Square size={16} className="fill-current" />
                </button>
              )}
            </div>
          </div>
        </div>
        )
  }
  return <div ref={list} className="space-y-3 video-task-list">
    {groupVideoCollections(videos).map(group=>group.collection ? <details key={group.key} className="video-collection rounded-xl border border-dark-border bg-dark-surface p-3">
      <summary>
        <CachedImage src={group.tasks.find(task=>task.thumbnail)?.thumbnail||''} alt="" fit="contain" className="series-channel-cover" fallback={<span className="cached-image-fallback" aria-hidden="true"><Video size={32}/></span>}/>
        <span className="series-channel-copy"><span className="series-meta">Bilibili</span><strong>{group.title}</strong><span className="series-meta">{group.tasks[0].channel}</span>
          <span className="series-channel-footer"><span>{group.total>1?`${group.total} episodes`:'Series'} · {group.tasks.filter(task=>task.status==='success').length} ready in this list</span><span className="series-channel-toggle"><span className="series-show">View episodes ⌄</span><span className="series-hide">Hide episodes ⌃</span></span></span>
        </span>
      </summary>
      <div className="mt-3 space-y-3">{group.tasks.map(renderTask)}</div>
    </details> : group.tasks.map(renderTask))}
  </div>
}
