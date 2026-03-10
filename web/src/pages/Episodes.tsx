import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Play, FileText, MessageSquare, Loader2, CheckCircle, Trash2, RefreshCw, Tag, Sparkles, Upload } from 'lucide-react'
import { fetchPodcast, fetchEpisodes, processEpisode, deleteEpisode, resummarizeEpisode, uploadLocalPodcastAudio, type Podcast, type Episode } from '../lib/api'
import { useToast } from '../components/Toast'
import { useStore } from '../lib/store'
import { getStatusColor } from '../lib/statusUtils'
import { markSeen, isNewItem } from '../lib/seen'

export default function Episodes() {
  const { pid } = useParams<{ pid: string }>()
  const [podcast, setPodcast] = useState<Podcast | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [processingEid, setProcessingEid] = useState<string | null>(null)
  const [regeneratingEid, setRegeneratingEid] = useState<string | null>(null)
  const [deletingEid, setDeletingEid] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { jobs, updateJob } = useStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  // Helper to find active job for an episode
  function getActiveJob(eid: string) {
    return jobs.find(job => 
      job.episode_id === eid && 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
  }
  
  useEffect(() => {
    if (pid) loadData()
  }, [pid])

  const seenMarkedRef = useRef(false)
  useEffect(() => {
    if (episodes.length > 0 && !seenMarkedRef.current) {
      seenMarkedRef.current = true
      markSeen(episodes.map(e => e.eid))
    }
  }, [episodes])
  
  async function loadData() {
    try {
      const [podcastData, episodesData] = await Promise.all([
        fetchPodcast(pid!),
        fetchEpisodes(pid!),
      ])
      setPodcast(podcastData)
      setEpisodes(episodesData)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleProcess(episode: Episode) {
    setProcessingEid(episode.eid)
    try {
      const isLocal = podcast?.platform === 'local'
      const isApple = podcast?.platform === 'apple'
      const episodeUrl = isLocal
        ? `local://${episode.eid}`
        : isApple
          ? `apple://${episode.eid}`
          : `https://www.xiaoyuzhoufm.com/episode/${episode.eid}`
      const result = await processEpisode(episodeUrl)
      
      // Immediately add job to store for instant UI feedback
      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Starting...',
        episode_id: episode.eid,
        episode_title: episode.title,
      })
      
      addToast({
        type: 'success',
        title: 'Processing started',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to start processing:', err)
      addToast({
        type: 'error',
        title: 'Failed to start processing',
      })
    } finally {
      setProcessingEid(null)
    }
  }

  async function handleLocalUpload(file: File) {
    setUploading(true)
    try {
      const result = await uploadLocalPodcastAudio(file, {
        title: uploadTitle.trim(),
        description: uploadDescription.trim(),
      })
      if (result.podcast.pid === pid) {
        setEpisodes(prev => [result.episode, ...prev])
      } else {
        await loadData()
      }
      setUploadTitle('')
      setUploadDescription('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      addToast({ type: 'success', title: 'Audio uploaded', message: result.episode.title })
    } catch (err) {
      console.error('Failed to upload audio:', err)
      addToast({
        type: 'error',
        title: 'Upload failed',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setUploading(false)
    }
  }
  
  async function handleRegenerate(episode: Episode) {
    setRegeneratingEid(episode.eid)
    try {
      const result = await resummarizeEpisode(episode.eid)
      
      // Add job to store for instant UI feedback
      updateJob({
        job_id: result.job_id,
        status: 'pending',
        progress: 0,
        message: 'Re-summarizing...',
        episode_id: episode.eid,
        episode_title: episode.title,
      })
      
      addToast({
        type: 'success',
        title: 'Re-summarization started',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to start re-summarization:', err)
      addToast({
        type: 'error',
        title: 'Failed to start re-summarization',
      })
    } finally {
      setRegeneratingEid(null)
    }
  }
  
  async function handleDelete(episode: Episode) {
    if (!confirm(`Delete "${episode.title}"?\n\nThis will also delete any transcript and summary.`)) {
      return
    }
    
    setDeletingEid(episode.eid)
    try {
      await deleteEpisode(episode.eid)
      setEpisodes(episodes.filter(e => e.eid !== episode.eid))
      addToast({
        type: 'success',
        title: 'Episode deleted',
        message: episode.title,
      })
    } catch (err) {
      console.error('Failed to delete episode:', err)
      addToast({
        type: 'error',
        title: 'Failed to delete episode',
      })
    } finally {
      setDeletingEid(null)
    }
  }
  
  function formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60)
    return `${mins} min`
  }
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }
  
  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-center gap-3 md:gap-4">
        <button
          onClick={() => navigate(-1)}
          className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="min-w-0">
          <h1 className="text-lg md:text-2xl font-bold text-white line-clamp-1">{podcast?.title || 'Episodes'}</h1>
          <p className="text-sm md:text-base text-gray-400">{episodes.length} episodes</p>
        </div>
      </div>

      {podcast?.platform === 'local' && (
        <div className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-white">Add More Local Audio</h2>
              <p className="text-sm text-gray-400">New uploads are added to this local podcast and can be processed like normal episodes.</p>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors"
            >
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              Upload Audio
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              type="text"
              value={uploadTitle}
              onChange={e => setUploadTitle(e.target.value)}
              placeholder="Optional title override"
              className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*,.mp3,.m4a,.wav,.aac,.flac,.ogg,.opus,.mp4,.mpeg,.mpga"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) void handleLocalUpload(file)
              }}
            />
            <textarea
              value={uploadDescription}
              onChange={e => setUploadDescription(e.target.value)}
              placeholder="Optional description"
              rows={2}
              className="md:col-span-2 w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base resize-y"
            />
          </div>
        </div>
      )}
      
      {/* Episodes list */}
      <div className="space-y-3">
        {episodes.map((episode) => (
          <div
            key={episode.eid}
            onClick={episode.has_summary ? () => navigate(`/viewer/${episode.eid}`) : undefined}
            className={`p-3 md:p-4 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors${episode.has_summary ? ' cursor-pointer' : ''}`}
          >
            <div className="flex flex-col sm:flex-row sm:items-start gap-3 md:gap-4">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-white mb-1 line-clamp-2 text-sm md:text-base">
                  {episode.title}
                </h3>
                <div className="flex flex-wrap items-center gap-2 md:gap-4 text-xs md:text-sm text-gray-400">
                  {episode.pub_date && <span>{episode.pub_date.slice(0, 10)}</span>}
                  {episode.created_at && episode.created_at.slice(0, 10) !== (episode.pub_date || '').slice(0, 10) && (
                    <span className="text-gray-500">imported {episode.created_at.slice(0, 10)}</span>
                  )}
                  <span>{formatDuration(episode.duration)}</span>
                  
                  {/* Status indicators */}
                  {episode.has_transcript && (
                    <span className="flex items-center gap-1 text-green-500">
                      <FileText size={12} className="md:w-3.5 md:h-3.5" />
                      <span className="hidden sm:inline">Transcript</span>
                    </span>
                  )}
                  {episode.has_summary && (
                    <span className="flex items-center gap-1 text-purple-500">
                      <MessageSquare size={12} className="md:w-3.5 md:h-3.5" />
                      <span className="hidden sm:inline">Summary</span>
                      <span className="text-gray-400 ml-1">
                        ({episode.topics_count} <Tag size={10} className="inline" />, {episode.key_points_count} pts)
                      </span>
                    </span>
                  )}
                  {!episode.has_transcript && !episode.has_summary && isNewItem(episode.eid) && (
                    <span className="flex items-center gap-1 text-cyan-400">
                      <Sparkles size={12} className="md:w-3.5 md:h-3.5" />
                      <span className="hidden sm:inline">Newly Added</span>
                    </span>
                  )}
                </div>
              </div>
              
              <div className="flex items-center gap-2 justify-end sm:justify-start" onClick={e => e.stopPropagation()}>
                {(() => {
                  const activeJob = getActiveJob(episode.eid)
                  
                  if (episode.has_summary) {
                    return (
                      <>
                        <button
                          onClick={() => handleRegenerate(episode)}
                          disabled={regeneratingEid === episode.eid || !!activeJob}
                          className="flex items-center gap-2 px-3 py-2 bg-dark-hover hover:bg-dark-border text-gray-300 rounded-lg transition-colors disabled:opacity-50"
                          title="Re-process episode"
                        >
                          {regeneratingEid === episode.eid ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <RefreshCw size={16} />
                          )}
                          <span className="hidden sm:inline">Re-Process</span>
                        </button>
                        <Link
                          to={`/viewer/${episode.eid}`}
                          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
                        >
                          <CheckCircle size={16} />
                          View
                        </Link>
                      </>
                    )
                  }
                  
                  if (activeJob) {
                    // Show processing progress
                    return (
                      <div className="flex items-center gap-3 px-4 py-2 bg-dark-hover rounded-lg min-w-[140px]">
                        <Loader2 size={16} className="animate-spin text-indigo-400" />
                        <div className="flex-1">
                          <div className="text-xs text-gray-400 mb-1">
                            {activeJob.message || activeJob.status}
                          </div>
                          <div className="h-1.5 bg-dark-border rounded-full overflow-hidden">
                            <div 
                              className={`h-full ${getStatusColor(activeJob.status)} transition-all duration-300`}
                              style={{ width: `${Math.min(activeJob.progress, 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    )
                  }
                  
                  return (
                    <button
                      onClick={() => handleProcess(episode)}
                      disabled={processingEid === episode.eid}
                      className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                    >
                      {processingEid === episode.eid ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Play size={16} />
                      )}
                      Process
                    </button>
                  )
                })()}
                
                {/* Delete button */}
                <button
                  onClick={() => handleDelete(episode)}
                  disabled={deletingEid === episode.eid}
                  className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors disabled:opacity-50"
                  title="Delete episode"
                >
                  {deletingEid === episode.eid ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
