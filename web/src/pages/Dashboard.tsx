import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Radio, FileText, MessageSquare, Loader2, Plus, ArrowRight, Bell, RefreshCw, X, Video, CheckCircle, Users } from 'lucide-react'
import { fetchStats, fetchSummaries, processEpisode, fetchNewEpisodes, checkPodcastsForUpdates, checkVideoChannelsForUpdates, fetchVideoTasks, cancelJob, cancelVideoTask, generateVideoNote, getVideoProcessingDefaults, getUserModelSettings, type Stats, type SummaryListItem, type ProcessingJob, type NewEpisode, type VideoTask } from '../lib/api'
import { useStore } from '../lib/store'
import { getCache, setCache, CacheKeys } from '../lib/cache'
import { useToast } from '../components/Toast'
import { markSeen, shouldDismissCompleted } from '../lib/seen'
import SummaryCard from '../components/SummaryCard'
import ProcessingProgress from '../components/ProcessingProgress'

const VIDEO_QUEUE_STATUSES = new Set(['pending', 'parsing', 'downloading', 'transcribing', 'summarizing', 'saving', 'success', 'failed'])

function detectVideoPlatform(url: string): string {
  const u = url.toLowerCase()
  if (/bilibili\.com|b23\.tv/.test(u)) return 'bilibili'
  if (/youtube\.com|youtu\.be/.test(u)) return 'youtube'
  if (/douyin\.com|tiktok\.com/.test(u)) return 'douyin'
  if (/kuaishou\.com|kwai\.com/.test(u)) return 'kuaishou'
  return ''
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [summaries, setSummaries] = useState<SummaryListItem[]>([])
  const [recentVideos, setRecentVideos] = useState<VideoTask[]>([])
  const [videoChannels, setVideoChannels] = useState<{ name: string; avatar: string; url: string; count: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [episodeUrl, setEpisodeUrl] = useState('')
  const [processing, setProcessing] = useState(false)
  const [newEpisodes, setNewEpisodes] = useState<NewEpisode[]>([])
  const [checkingUpdates, setCheckingUpdates] = useState(false)
  const [showNewEpisodes, setShowNewEpisodes] = useState(true)

  const { jobs, updateJob, removeJob, videoTasks, setVideoTasks } = useStore()
  const { addToast } = useToast()

  async function handleCancelQueueItem(id: string, kind: 'podcast' | 'video') {
    try {
      if (kind === 'podcast') {
        await cancelJob(id)
        removeJob(id)
      } else {
        await cancelVideoTask(id)
        setVideoTasks(videoTasks.filter(t => t.id !== id))
      }
      addToast({ type: 'info', title: 'Cancelled', message: 'Task has been cancelled' })
    } catch (err) {
      addToast({ type: 'error', title: 'Cancel failed', message: err instanceof Error ? err.message : 'Unknown error' })
    }
  }

  const activeVideoJobs: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => VIDEO_QUEUE_STATUSES.has(t.status) && t.status !== 'success' && t.status !== 'failed')
      .map(t => ({
        job_id: t.id,
        status: t.status === 'saving' ? 'summarizing' : t.status,
        progress: t.progress,
        message: t.message || t.title || '',
        episode_title: t.title || (t.url ? (() => { try { return new URL(t.url).hostname + new URL(t.url).pathname.slice(0, 30) } catch { return t.url } })() : 'Video'),
      }))
  }, [videoTasks])

  const recentlyDoneVideos: ProcessingJob[] = useMemo(() => {
    return videoTasks
      .filter(t => (t.status === 'success' || t.status === 'failed') && !shouldDismissCompleted(t.id))
      .slice(0, 3)
      .map(t => ({
        job_id: t.id,
        status: t.status,
        progress: 100,
        message: t.status === 'success' ? 'Notes generated!' : (t.error || t.message || 'Failed'),
        episode_title: t.title || 'Video',
      }))
  }, [videoTasks])

  const allQueueItems = useMemo(() => {
    const activePodcasts = jobs
      .filter(j => j.status !== 'completed' && j.status !== 'failed' && j.status !== 'cancelled')
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const donePodcasts = jobs
      .filter(j => (j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled') && !shouldDismissCompleted(j.job_id))
      .map(j => ({ ...j, _kind: 'podcast' as const }))
    const videoJobs = activeVideoJobs.map(j => ({ ...j, _kind: 'video' as const }))
    const doneVideos = recentlyDoneVideos.slice(0, 2).map(j => ({ ...j, _kind: 'video' as const }))

    return [...activePodcasts, ...videoJobs, ...donePodcasts, ...doneVideos]
  }, [jobs, activeVideoJobs, recentlyDoneVideos])

  // Mark completed queue items as seen so they auto-dismiss on next load
  const queueSeenRef = useRef(false)
  useEffect(() => {
    const doneIds = [
      ...jobs.filter(j => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled').map(j => j.job_id),
      ...videoTasks.filter(t => t.status === 'success' || t.status === 'failed').map(t => t.id),
    ]
    if (doneIds.length > 0 && !queueSeenRef.current) {
      queueSeenRef.current = true
      markSeen(doneIds)
    }
  }, [jobs, videoTasks])

  useEffect(() => {
    loadData()
    loadNewEpisodes()
  }, [])

  async function loadData() {
    const cachedStats = getCache<Stats>(CacheKeys.STATS)
    const cachedSummaries = getCache<SummaryListItem[]>(CacheKeys.SUMMARIES)

    if (cachedStats) setStats(cachedStats)
    if (cachedSummaries) setSummaries(cachedSummaries)
    if (cachedStats || cachedSummaries) setLoading(false)

    try {
      const [statsData, summariesData, videoData] = await Promise.all([
        fetchStats(),
        fetchSummaries(),
        fetchVideoTasks().catch(() => ({ tasks: [] })),
      ])
      setStats(statsData)
      const sorted = [...summariesData].sort((a, b) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      )
      setSummaries(sorted)

      if (videoData.tasks.length > 0) setVideoTasks(videoData.tasks)
      const successTasks = videoData.tasks
        .filter(t => t.status === 'success')
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      setRecentVideos(successTasks.slice(0, 6))

      const channelMap = new Map<string, { name: string; avatar: string; url: string; count: number }>()
      for (const t of successTasks) {
        if (!t.channel) continue
        const existing = channelMap.get(t.channel)
        if (existing) {
          existing.count++
        } else {
          channelMap.set(t.channel, { name: t.channel, avatar: t.channel_avatar || '', url: t.channel_url || '', count: 1 })
        }
      }
      setVideoChannels(Array.from(channelMap.values()).sort((a, b) => b.count - a.count))

      setCache(CacheKeys.STATS, statsData)
      setCache(CacheKeys.SUMMARIES, summariesData)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  async function loadNewEpisodes() {
    try {
      const data = await fetchNewEpisodes()
      setNewEpisodes(data.episodes || [])
    } catch (err) {
      console.error('Failed to load new episodes:', err)
    }
  }

  async function handleCheckUpdates() {
    setCheckingUpdates(true)
    try {
      const [podcastResult, videoResult] = await Promise.all([
        checkPodcastsForUpdates().catch(e => {
          console.error('Podcast check failed:', e)
          return { new_episodes: 0, episodes: [] as NewEpisode[], message: '' }
        }),
        checkVideoChannelsForUpdates().catch(e => {
          console.error('Video channel check failed:', e)
          return { new_videos: 0, channels_checked: 0, message: '' }
        }),
      ])

      const hasNewPodcasts = podcastResult.new_episodes > 0
      const hasNewVideos = videoResult.new_videos > 0

      if (hasNewPodcasts) {
        setNewEpisodes(podcastResult.episodes)
        setShowNewEpisodes(true)
      }

      if (hasNewPodcasts && hasNewVideos) {
        addToast({ type: 'success', title: 'New content found', message: `${podcastResult.new_episodes} episode(s) + ${videoResult.new_videos} video(s)` })
        loadData()
      } else if (hasNewPodcasts) {
        addToast({ type: 'success', title: 'New episodes found', message: `Found ${podcastResult.new_episodes} new episode(s)` })
        loadData()
      } else if (hasNewVideos) {
        addToast({ type: 'success', title: 'New videos found', message: `Found ${videoResult.new_videos} new video(s) from ${videoResult.channels_checked} channel(s)` })
        loadData()
      } else {
        addToast({ type: 'info', title: 'All caught up', message: 'No new episodes or videos found' })
      }
    } catch (err) {
      console.error('Failed to check for updates:', err)
      addToast({ type: 'error', title: 'Failed to check updates', message: err instanceof Error ? err.message : 'Unknown error' })
    } finally {
      setCheckingUpdates(false)
    }
  }

  async function handleProcess(e: React.FormEvent) {
    e.preventDefault()
    const url = episodeUrl.trim()
    if (!url) return

    setProcessing(true)
    try {
      const videoPlatform = detectVideoPlatform(url)
      if (videoPlatform) {
        const defaults = getVideoProcessingDefaults()
        const modelSettings = getUserModelSettings()
        await generateVideoNote({
          url,
          platform: videoPlatform,
          style: (defaults.style as string) || 'detailed',
          formats: (defaults.formats as string[]) || ['toc', 'summary', 'screenshot'],
          quality: (defaults.quality as string) || 'medium',
          video_quality: (defaults.video_quality as string) || '720',
          llm_model: modelSettings.llm_model,
        })
        setEpisodeUrl('')
        addToast({ type: 'success', title: 'Video processing started', message: 'Check the processing panel for progress' })
        loadData()
      } else {
        const result = await processEpisode(url)
        updateJob({
          job_id: result.job_id,
          status: 'pending',
          progress: 0,
          message: 'Starting...',
          episode_id: result.episode_id,
          episode_title: result.episode_title,
        })
        setEpisodeUrl('')
        addToast({ type: 'success', title: 'Processing started', message: 'Check the processing panel for progress' })
      }
    } catch (err) {
      console.error('Failed to start processing:', err)
      addToast({ type: 'error', title: 'Failed to start processing', message: err instanceof Error ? err.message : 'Unknown error' })
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Dashboard</h1>
          <p className="text-gray-400">Manage your podcasts and video notes</p>
        </div>
        <button
          onClick={handleCheckUpdates}
          disabled={checkingUpdates}
          className="flex items-center gap-2 px-3 py-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
          title="Check podcasts and video channels for new content"
        >
          <RefreshCw size={16} className={checkingUpdates ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">{checkingUpdates ? 'Checking...' : 'Check Updates'}</span>
        </button>
      </div>

      {/* New episodes notification */}
      {showNewEpisodes && newEpisodes.length > 0 && (
        <div className="p-4 bg-indigo-900/30 border border-indigo-500/30 rounded-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Bell className="w-5 h-5 text-indigo-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-white mb-2">
                  {newEpisodes.length} New Episode{newEpisodes.length > 1 ? 's' : ''} Available
                </h3>
                <div className="space-y-1">
                  {newEpisodes.slice(0, 5).map((ep) => (
                    <Link
                      key={ep.eid}
                      to={`/podcasts/${ep.podcast_pid}/episodes`}
                      className="block text-sm text-gray-300 hover:text-indigo-300 transition-colors"
                    >
                      <span className="text-indigo-400">{ep.podcast_title}:</span> {ep.title}
                    </Link>
                  ))}
                  {newEpisodes.length > 5 && (
                    <p className="text-sm text-gray-500">+{newEpisodes.length - 5} more</p>
                  )}
                </div>
              </div>
            </div>
            <button onClick={() => setShowNewEpisodes(false)} className="p-1 text-gray-400 hover:text-white transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Quick process form */}
      <div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Process</h2>
        <form onSubmit={handleProcess} className="flex flex-col sm:flex-row gap-3 sm:gap-4">
          <input
            type="text"
            value={episodeUrl}
            onChange={(e) => setEpisodeUrl(e.target.value)}
            placeholder="Paste podcast episode or video URL..."
            className="flex-1 px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
          />
          <button
            type="submit"
            disabled={processing || !episodeUrl.trim()}
            className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            {processing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
            Process
          </button>
        </form>
      </div>

      {/* Stats — podcast + video combined */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3 md:gap-4">
          <StatCard icon={Radio} label="Podcasts" value={stats.total_podcasts} color="text-indigo-500" />
          <StatCard icon={FileText} label="Episodes" value={stats.total_episodes} color="text-blue-500" />
          <StatCard icon={FileText} label="Transcripts" value={stats.total_transcripts} color="text-green-500" />
          <StatCard icon={MessageSquare} label="Summaries" value={stats.total_summaries} color="text-purple-500" />
          <StatCard icon={Users} label="Channels" value={videoChannels.length} color="text-orange-500" />
          <StatCard icon={Video} label="Videos" value={stats.total_videos} color="text-cyan-500" />
          <StatCard icon={CheckCircle} label="Completed" value={stats.completed_videos} color="text-emerald-500" />
        </div>
      )}

      {/* Processing jobs — podcast + video combined */}
      {allQueueItems.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-white mb-4">Processing Queue</h2>
          <div className="space-y-3">
            {allQueueItems.map((item) => {
              const isVideo = item._kind === 'video'
              const isDone = item.status === 'completed' || item.status === 'success'
              const link = isDone
                ? isVideo ? `/videos/${item.job_id}` : item.episode_id ? `/viewer/${item.episode_id}` : undefined
                : undefined
              return (
                <ProcessingProgress
                  key={`${item._kind}-${item.job_id}`}
                  job={item}
                  link={link}
                  kind={item._kind}
                  onCancel={(id) => handleCancelQueueItem(id, item._kind)}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Two-column: Recent summaries + Recent video notes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent podcast summaries */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Summaries</h2>
            <Link
              to="/podcasts"
              className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
            >
              View all <ArrowRight size={16} />
            </Link>
          </div>
          {summaries.length === 0 ? (
            <div className="p-8 bg-dark-surface border border-dark-border rounded-xl text-center">
              <FileText className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">No summaries yet</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {summaries.slice(0, 4).map((summary) => (
                <SummaryCard key={summary.episode_id} summary={summary} />
              ))}
            </div>
          )}
        </div>

        {/* Recent video notes */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Video Notes</h2>
            <Link
              to="/videos"
              className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
            >
              View all <ArrowRight size={16} />
            </Link>
          </div>
          {recentVideos.length === 0 ? (
            <div className="p-8 bg-dark-surface border border-dark-border rounded-xl text-center">
              <Video className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 text-sm">No video notes yet</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {recentVideos.slice(0, 4).map((task) => (
                <Link
                  key={task.id}
                  to={`/videos/${task.id}`}
                  className="flex gap-4 p-4 min-h-[104px] bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors"
                >
                  {task.thumbnail ? (
                    <img
                      src={task.thumbnail}
                      alt=""
                      className="w-20 h-14 rounded object-cover flex-shrink-0 bg-dark-hover my-auto"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="w-20 h-14 rounded bg-dark-hover flex items-center justify-center flex-shrink-0 my-auto">
                      <Video size={16} className="text-gray-600" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0 flex flex-col justify-between">
                    <h3 className="font-medium text-white line-clamp-2">
                      {task.title || (task.url ? (() => {
                        if (task.platform === 'local') {
                          const parts = task.url.split(/[\\/]/)
                          const filename = parts[parts.length - 1] || task.url
                          return filename.replace(/\.[^.]+$/, '')
                        }
                        try { return new URL(task.url).hostname.replace('www.', '') + new URL(task.url).pathname.replace(/\/$/, '').slice(0, 30) }
                        catch { return 'Untitled' }
                      })() : 'Untitled')}
                    </h3>
                    <div className="flex items-center gap-4 text-sm text-gray-400 mt-auto">
                      {task.channel && (
                        <span className="flex items-center gap-1.5 truncate">
                          {task.channel_avatar ? (
                            <img src={task.channel_avatar} alt="" className="w-4 h-4 rounded-full flex-shrink-0 bg-dark-hover" referrerPolicy="no-referrer" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                          ) : (
                            <Video size={14} className="text-cyan-400 flex-shrink-0" />
                          )}
                          <span className="truncate">{task.channel}</span>
                        </span>
                      )}
                      {task.style && <span className="px-1.5 py-0.5 bg-purple-600/20 text-purple-400 rounded-full text-[10px]">{task.style}</span>}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  color
}: {
  icon: typeof Radio
  label: string
  value: number
  color: string
}) {
  return (
    <div className="p-4 bg-dark-surface border border-dark-border rounded-xl">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg bg-dark-hover ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xl font-bold text-white">{value}</p>
          <p className="text-xs text-gray-400">{label}</p>
        </div>
      </div>
    </div>
  )
}
