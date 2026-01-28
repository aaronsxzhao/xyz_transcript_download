import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Radio, Plus, Trash2, RefreshCw, Loader2, ExternalLink } from 'lucide-react'
import { fetchPodcasts, addPodcast, removePodcast, refreshPodcast, type Podcast } from '../lib/api'
import { useToast } from '../components/Toast'

export default function Podcasts() {
  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [refreshing, setRefreshing] = useState<string | null>(null)
  const [deletingPid, setDeletingPid] = useState<string | null>(null)
  const { addToast, removeToast } = useToast()
  
  useEffect(() => {
    loadPodcasts()
  }, [])
  
  async function loadPodcasts() {
    try {
      const data = await fetchPodcasts()
      setPodcasts(data)
    } catch (err) {
      console.error('Failed to load podcasts:', err)
    } finally {
      setLoading(false)
    }
  }
  
  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!newUrl.trim()) return
    
    setAdding(true)
    const toastId = addToast({
      type: 'loading',
      title: 'Adding podcast...',
      message: 'Fetching podcast information',
    })
    
    try {
      const podcast = await addPodcast(newUrl)
      setPodcasts([podcast, ...podcasts])
      setNewUrl('')
      setShowAddForm(false)
      removeToast(toastId)
      addToast({
        type: 'success',
        title: 'Podcast added',
        message: podcast.title,
      })
    } catch (err: unknown) {
      removeToast(toastId)
      addToast({
        type: 'error',
        title: 'Failed to add podcast',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setAdding(false)
    }
  }
  
  async function handleRemove(pid: string) {
    if (!confirm('Remove this podcast?')) return
    
    const podcast = podcasts.find(p => p.pid === pid)
    setDeletingPid(pid)
    
    try {
      await removePodcast(pid)
      setPodcasts(podcasts.filter(p => p.pid !== pid))
      addToast({
        type: 'success',
        title: 'Podcast removed',
        message: podcast?.title || 'Podcast unsubscribed',
      })
    } catch (err) {
      console.error('Failed to remove podcast:', err)
      addToast({
        type: 'error',
        title: 'Failed to remove podcast',
      })
    } finally {
      setDeletingPid(null)
    }
  }
  
  async function handleRefresh(pid: string) {
    setRefreshing(pid)
    try {
      const result = await refreshPodcast(pid)
      addToast({
        type: 'success',
        title: 'Podcast refreshed',
        message: result.message,
      })
      loadPodcasts()
    } catch (err) {
      console.error('Failed to refresh podcast:', err)
      addToast({
        type: 'error',
        title: 'Failed to refresh podcast',
      })
    } finally {
      setRefreshing(null)
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Podcasts</h1>
          <p className="text-gray-400">Manage your subscribed podcasts</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors"
        >
          <Plus size={20} />
          Add Podcast
        </button>
      </div>
      
      {/* Add form */}
      {showAddForm && (
        <div className="p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Add New Podcast</h2>
          <form onSubmit={handleAdd} className="flex gap-4">
            <input
              type="url"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="Paste podcast URL (e.g., https://www.xiaoyuzhoufm.com/podcast/...)"
              className="flex-1 px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={adding || !newUrl.trim()}
              className="flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {adding ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
              Add
            </button>
          </form>
        </div>
      )}
      
      {/* Podcast list */}
      {podcasts.length === 0 ? (
        <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
          <Radio className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <p className="text-xl text-gray-400 mb-2">No podcasts yet</p>
          <p className="text-gray-500">Add a podcast to get started</p>
        </div>
      ) : (
        <div className="space-y-4">
          {podcasts.map((podcast) => (
            <div
              key={podcast.pid}
              className="p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors"
            >
              <div className="flex items-start gap-4">
                <PodcastImage url={podcast.cover_url} alt={podcast.title} />
                
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-semibold text-white mb-1 truncate">
                    {podcast.title}
                  </h3>
                  {podcast.author && (
                    <p className="text-sm text-gray-400 mb-2">{podcast.author}</p>
                  )}
                  <p className="text-sm text-gray-500 line-clamp-2">
                    {podcast.description || 'No description'}
                  </p>
                  <p className="text-sm text-indigo-400 mt-2">
                    {podcast.episode_count} episodes
                  </p>
                </div>
                
                <div className="flex items-center gap-2">
                  <Link
                    to={`/podcasts/${podcast.pid}/episodes`}
                    className="flex items-center gap-1 px-3 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors"
                  >
                    <ExternalLink size={16} />
                    Episodes
                  </Link>
                  <button
                    onClick={() => handleRefresh(podcast.pid)}
                    disabled={refreshing === podcast.pid}
                    className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                    title="Refresh episodes"
                  >
                    <RefreshCw size={16} className={refreshing === podcast.pid ? 'animate-spin' : ''} />
                  </button>
                  <button
                    onClick={() => handleRemove(podcast.pid)}
                    disabled={deletingPid === podcast.pid}
                    className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors disabled:opacity-50"
                    title="Remove podcast"
                  >
                    {deletingPid === podcast.pid ? (
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
      )}
    </div>
  )
}

// Image component with proxy and error fallback
function PodcastImage({ url, alt }: { url?: string; alt: string }) {
  const [error, setError] = useState(false)
  
  if (!url || error) {
    return (
      <div className="w-20 h-20 rounded-lg bg-dark-hover flex items-center justify-center">
        <Radio className="w-8 h-8 text-gray-600" />
      </div>
    )
  }
  
  // Use proxy to avoid CORS issues
  const proxyUrl = `/api/image-proxy?url=${encodeURIComponent(url)}`
  
  return (
    <img
      src={proxyUrl}
      alt={alt}
      className="w-20 h-20 rounded-lg object-cover bg-dark-hover"
      onError={() => setError(true)}
    />
  )
}
