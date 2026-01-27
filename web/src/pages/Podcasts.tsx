import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Radio, Plus, Trash2, RefreshCw, Loader2, ExternalLink } from 'lucide-react'
import { fetchPodcasts, addPodcast, removePodcast, refreshPodcast, type Podcast } from '../lib/api'

export default function Podcasts() {
  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [refreshing, setRefreshing] = useState<string | null>(null)
  
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
    try {
      const podcast = await addPodcast(newUrl)
      setPodcasts([podcast, ...podcasts])
      setNewUrl('')
      setShowAddForm(false)
    } catch (err: any) {
      alert(err.message || 'Failed to add podcast')
    } finally {
      setAdding(false)
    }
  }
  
  async function handleRemove(pid: string) {
    if (!confirm('Remove this podcast?')) return
    
    try {
      await removePodcast(pid)
      setPodcasts(podcasts.filter(p => p.pid !== pid))
    } catch (err) {
      console.error('Failed to remove podcast:', err)
    }
  }
  
  async function handleRefresh(pid: string) {
    setRefreshing(pid)
    try {
      const result = await refreshPodcast(pid)
      alert(result.message)
      loadPodcasts()
    } catch (err) {
      console.error('Failed to refresh podcast:', err)
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
                {podcast.cover_url ? (
                  <img
                    src={podcast.cover_url}
                    alt={podcast.title}
                    className="w-20 h-20 rounded-lg object-cover"
                  />
                ) : (
                  <div className="w-20 h-20 rounded-lg bg-dark-hover flex items-center justify-center">
                    <Radio className="w-8 h-8 text-gray-600" />
                  </div>
                )}
                
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
                    className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors"
                    title="Remove podcast"
                  >
                    <Trash2 size={16} />
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
