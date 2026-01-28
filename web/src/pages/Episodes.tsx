import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Play, FileText, MessageSquare, Loader2, CheckCircle, Trash2 } from 'lucide-react'
import { fetchPodcast, fetchEpisodes, processEpisode, deleteEpisode, type Podcast, type Episode } from '../lib/api'
import { useToast } from '../components/Toast'

export default function Episodes() {
  const { pid } = useParams<{ pid: string }>()
  const [podcast, setPodcast] = useState<Podcast | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [processingEid, setProcessingEid] = useState<string | null>(null)
  const [deletingEid, setDeletingEid] = useState<string | null>(null)
  const { addToast } = useToast()
  
  useEffect(() => {
    if (pid) loadData()
  }, [pid])
  
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
      const episodeUrl = `https://www.xiaoyuzhoufm.com/episode/${episode.eid}`
      await processEpisode(episodeUrl)
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
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/podcasts"
          className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors"
        >
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-white">{podcast?.title || 'Episodes'}</h1>
          <p className="text-gray-400">{episodes.length} episodes</p>
        </div>
      </div>
      
      {/* Episodes list */}
      <div className="space-y-3">
        {episodes.map((episode) => (
          <div
            key={episode.eid}
            className="p-4 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
          >
            <div className="flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-white mb-1 line-clamp-2">
                  {episode.title}
                </h3>
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span>{episode.pub_date?.slice(0, 10)}</span>
                  <span>{formatDuration(episode.duration)}</span>
                  
                  {/* Status indicators */}
                  {episode.has_transcript && (
                    <span className="flex items-center gap-1 text-green-500">
                      <FileText size={14} />
                      Transcript
                    </span>
                  )}
                  {episode.has_summary && (
                    <span className="flex items-center gap-1 text-purple-500">
                      <MessageSquare size={14} />
                      Summary
                    </span>
                  )}
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                {episode.has_summary ? (
                  <Link
                    to={`/viewer/${episode.eid}`}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
                  >
                    <CheckCircle size={16} />
                    View
                  </Link>
                ) : (
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
                )}
                
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
