import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Radio, Plus, Trash2, RefreshCw, Loader2, ExternalLink, ArrowLeft, ChevronRight, Search, Upload } from 'lucide-react'
import { fetchPodcasts, addPodcast, removePodcast, refreshPodcast, uploadLocalPodcastAudio, type Podcast } from '../lib/api'
import { useToast } from '../components/Toast'
import PlatformIcon, { PLATFORM_COLORS } from '../components/PlatformIcon'

const PODCAST_PLATFORMS: { id: string; label: string }[] = [
  { id: 'xiaoyuzhou', label: '小宇宙' },
  { id: 'apple', label: 'Apple Podcasts' },
  { id: 'local', label: 'Local Uploads' },
]

const PLATFORM_LABELS: Record<string, string> = {
  xiaoyuzhou: '小宇宙',
  apple: 'Apple Podcasts',
  local: 'Local Uploads',
}

type View =
  | { type: 'platforms' }
  | { type: 'podcasts'; platform: string }

function detectPlatform(url: string): string {
  const u = url.toLowerCase()
  if (/xiaoyuzhoufm\.com/.test(u)) return 'xiaoyuzhou'
  if (/podcasts\.apple\.com|itunes\.apple\.com/.test(u)) return 'apple'
  return ''
}

export default function Podcasts() {
  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [showUploadForm, setShowUploadForm] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [refreshing, setRefreshing] = useState<string | null>(null)
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [deletingPid, setDeletingPid] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()
  const { addToast, removeToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const view: View = useMemo(() => {
    const platform = searchParams.get('platform')
    if (platform) return { type: 'podcasts', platform }
    return { type: 'platforms' }
  }, [searchParams])

  const setView = useCallback((v: View) => {
    const params: Record<string, string> = {}
    if (v.type === 'podcasts') params.platform = v.platform
    setSearchParams(params, { replace: true })
  }, [setSearchParams])

  useEffect(() => { loadPodcasts() }, [])

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

  const detectedPlatform = useMemo(() => detectPlatform(newUrl), [newUrl])

  const filtered = useMemo(() => {
    if (!search) return podcasts
    const q = search.toLowerCase()
    return podcasts.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.author.toLowerCase().includes(q) ||
      p.description.toLowerCase().includes(q)
    )
  }, [podcasts, search])

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
      setPodcasts(prev => [podcast, ...prev])
      setNewUrl('')
      setShowAddForm(false)
      removeToast(toastId)
      addToast({ type: 'success', title: 'Podcast added', message: podcast.title })
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

  async function handleUploadAudio(e: React.FormEvent) {
    e.preventDefault()
    if (!audioFile) return

    setUploading(true)
    const toastId = addToast({
      type: 'loading',
      title: 'Uploading audio...',
      message: 'Creating your local podcast episode',
    })

    try {
      const result = await uploadLocalPodcastAudio(audioFile, {
        title: uploadTitle.trim(),
        description: uploadDescription.trim(),
      })
      removeToast(toastId)
      setAudioFile(null)
      setUploadTitle('')
      setUploadDescription('')
      setShowUploadForm(false)
      await loadPodcasts()
      addToast({ type: 'success', title: 'Audio uploaded', message: result.episode.title })
      navigate(`/podcasts/${result.podcast.pid}/episodes`)
    } catch (err: unknown) {
      removeToast(toastId)
      addToast({
        type: 'error',
        title: 'Upload failed',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      setUploading(false)
    }
  }

  async function handleRemove(pid: string) {
    if (!confirm('Remove this podcast?')) return
    const podcast = podcasts.find(p => p.pid === pid)
    setDeletingPid(pid)
    try {
      await removePodcast(pid)
      setPodcasts(prev => prev.filter(p => p.pid !== pid))
      addToast({ type: 'success', title: 'Podcast removed', message: podcast?.title || '' })
    } catch {
      addToast({ type: 'error', title: 'Failed to remove podcast' })
    } finally {
      setDeletingPid(null)
    }
  }

  async function handleRefresh(pid: string) {
    const podcast = podcasts.find(p => p.pid === pid)
    if ((podcast?.platform || 'xiaoyuzhou') === 'local') {
      addToast({ type: 'info', title: 'Local uploads', message: 'Uploaded audio is managed manually and does not support refresh.' })
      return
    }
    setRefreshing(pid)
    try {
      const result = await refreshPodcast(pid)
      addToast({ type: 'success', title: 'Podcast refreshed', message: result.message })
      loadPodcasts()
    } catch {
      addToast({ type: 'error', title: 'Failed to refresh podcast' })
    } finally {
      setRefreshing(null)
    }
  }

  async function handleCheckAllUpdates() {
    if (view.type !== 'podcasts') return
    if (view.platform === 'local') {
      addToast({ type: 'info', title: 'Local uploads', message: 'Local uploads do not have external updates to check.' })
      return
    }
    const platformPodcasts = podcasts.filter(p => (p.platform || 'xiaoyuzhou') === view.platform)
    if (platformPodcasts.length === 0) return

    setRefreshingAll(true)
    let totalNew = 0
    let checked = 0

    for (const podcast of platformPodcasts) {
      try {
        const result = await refreshPodcast(podcast.pid)
        const match = result.message?.match(/(\d+)/)
        if (match) totalNew += parseInt(match[1], 10)
      } catch {
        // continue checking others
      }
      checked++
    }

    setRefreshingAll(false)
    loadPodcasts()
    addToast({
      type: 'success',
      title: 'Check complete',
      message: totalNew > 0
        ? `Found ${totalNew} new episode${totalNew !== 1 ? 's' : ''} across ${checked} podcast${checked !== 1 ? 's' : ''}`
        : `No new episodes found (checked ${checked} podcast${checked !== 1 ? 's' : ''})`,
    })
  }

  const platformCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const p of filtered) {
      const plat = p.platform || 'xiaoyuzhou'
      counts[plat] = (counts[plat] || 0) + 1
    }
    return counts
  }, [filtered])

  const sortedPlatforms = useMemo(() => {
    const order = ['xiaoyuzhou', 'apple', 'local']
    return Object.keys(platformCounts).sort((a, b) =>
      (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
      (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
    )
  }, [platformCounts])

  const filteredPodcasts = useMemo(() => {
    if (view.type !== 'podcasts') return []
    return filtered.filter(p => (p.platform || 'xiaoyuzhou') === view.platform)
  }, [filtered, view])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {view.type === 'podcasts' && (
            <button
              onClick={() => setView({ type: 'platforms' })}
              className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
            >
              <ArrowLeft size={20} />
            </button>
          )}
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-white mb-1 md:mb-2">
              {view.type === 'podcasts'
                ? PLATFORM_LABELS[view.platform] || view.platform
                : 'Podcasts'}
            </h1>
            <p className="text-sm md:text-base text-gray-400">
              {view.type === 'podcasts'
                ? `${filteredPodcasts.length} podcast${filteredPodcasts.length !== 1 ? 's' : ''}`
                : 'Manage your subscribed podcasts'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          {view.type === 'podcasts' && view.platform !== 'local' && (
            <button
              onClick={handleCheckAllUpdates}
              disabled={refreshingAll}
              className="flex items-center justify-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border hover:bg-dark-hover text-white font-medium rounded-lg transition-colors disabled:opacity-50 flex-1 sm:flex-none"
              title="Check all podcasts for new episodes"
            >
              <RefreshCw size={18} className={refreshingAll ? 'animate-spin' : ''} />
              <span className="hidden sm:inline">Check Updates</span>
            </button>
          )}
          <button
            onClick={() => { setShowUploadForm(!showUploadForm); setShowAddForm(false) }}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border hover:bg-dark-hover text-white font-medium rounded-lg transition-colors flex-1 sm:flex-none"
          >
            <Upload size={18} />
            Upload Audio
          </button>
          <button
            onClick={() => { setShowAddForm(!showAddForm); setShowUploadForm(false) }}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors flex-1 sm:flex-none"
          >
            <Plus size={20} />
            Add Podcast
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAddForm && (
        <div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Add New Podcast</h2>
          <form onSubmit={handleAdd} className="flex flex-col sm:flex-row gap-3 sm:gap-4">
            <div className="flex-1 relative">
              <input
                type="text"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="Paste Xiaoyuzhou or Apple Podcasts URL..."
                className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
              />
              {detectedPlatform && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 px-2 py-1 rounded-md bg-dark-border text-xs text-gray-300">
                  <PlatformIcon platform={detectedPlatform} size={14} className={PLATFORM_COLORS[detectedPlatform] || ''} />
                  {PLATFORM_LABELS[detectedPlatform] || detectedPlatform}
                </span>
              )}
            </div>
            <button
              type="submit"
              disabled={adding || !newUrl.trim()}
              className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {adding ? <Loader2 className="w-5 h-5 animate-spin" /> : <Plus className="w-5 h-5" />}
              Add
            </button>
          </form>
        </div>
      )}

      {showUploadForm && (
        <div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Upload Local Audio</h2>
          <form onSubmit={handleUploadAudio} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Audio file</label>
                <input
                  type="file"
                  accept="audio/*,.mp3,.m4a,.wav,.aac,.flac,.ogg,.opus,.mp4,.mpeg,.mpga"
                  onChange={e => setAudioFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-gray-300 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-700"
                />
                {audioFile && <p className="mt-2 text-xs text-gray-500">{audioFile.name}</p>}
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-2">Episode title</label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={e => setUploadTitle(e.target.value)}
                  placeholder="Optional, defaults to filename"
                  className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Description</label>
              <textarea
                value={uploadDescription}
                onChange={e => setUploadDescription(e.target.value)}
                placeholder="Optional notes about this upload"
                rows={3}
                className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base resize-y"
              />
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
              <p className="text-sm text-gray-500">First upload creates your Local Uploads podcast automatically. Later uploads go into the same library section.</p>
              <button
                type="submit"
                disabled={uploading || !audioFile}
                className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                Upload
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search podcasts..."
          className="w-full pl-9 pr-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {/* Horizontal platform quick-select */}
      {sortedPlatforms.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            onClick={() => setView({ type: 'platforms' })}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
              view.type === 'platforms'
                ? 'bg-indigo-600 text-white'
                : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
            }`}
          >
            All ({filtered.length})
          </button>
          {sortedPlatforms.map(p => {
            const label = PLATFORM_LABELS[p] || p
            const count = platformCounts[p] || 0
            const isActive = view.type === 'podcasts' && view.platform === p
            return (
              <button
                key={p}
                onClick={() => setView({ type: 'podcasts', platform: p })}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
                }`}
              >
                <PlatformIcon platform={p} size={15} className={isActive ? 'text-white' : PLATFORM_COLORS[p] || 'text-gray-400'} />
                {label}
                <span className="text-xs opacity-70">({count})</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Platform View */}
      {view.type === 'platforms' && (
        <>
          {filtered.length === 0 ? (
            <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
              <Radio className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <p className="text-xl text-gray-400 mb-2">
                {search ? 'No matching podcasts' : 'No podcasts yet'}
              </p>
              <p className="text-gray-500">
                {search ? 'Try a different search term' : 'Add a podcast or upload local audio to get started'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {PODCAST_PLATFORMS.map(plat => {
                const count = platformCounts[plat.id] || 0
                if (count === 0) return null
                return (
                  <button
                    key={plat.id}
                    onClick={() => setView({ type: 'podcasts', platform: plat.id })}
                    className="p-5 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors text-left flex items-center gap-4"
                  >
                    <div className="w-12 h-12 rounded-xl bg-dark-hover flex items-center justify-center flex-shrink-0">
                      <PlatformIcon platform={plat.id} size={24} className={PLATFORM_COLORS[plat.id] || 'text-gray-400'} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-white">{plat.label}</h3>
                      <p className="text-sm text-gray-400">{count} podcast{count !== 1 ? 's' : ''}</p>
                    </div>
                    <ChevronRight size={20} className="text-gray-500" />
                  </button>
                )
              })}
              {Object.entries(platformCounts)
                .filter(([id]) => !PODCAST_PLATFORMS.some(p => p.id === id))
                .map(([id, count]) => (
                  <button
                    key={id}
                    onClick={() => setView({ type: 'podcasts', platform: id })}
                    className="p-5 bg-dark-surface border border-dark-border rounded-xl hover:border-indigo-500/50 transition-colors text-left flex items-center gap-4"
                  >
                    <div className="w-12 h-12 rounded-xl bg-dark-hover flex items-center justify-center flex-shrink-0">
                      <PlatformIcon platform={id} size={24} className={PLATFORM_COLORS[id] || 'text-gray-400'} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-white">{PLATFORM_LABELS[id] || id}</h3>
                      <p className="text-sm text-gray-400">{count} podcast{count !== 1 ? 's' : ''}</p>
                    </div>
                    <ChevronRight size={20} className="text-gray-500" />
                  </button>
                ))}
            </div>
          )}
        </>
      )}

      {/* Podcast List for a Platform */}
      {view.type === 'podcasts' && (
        <>
          {filteredPodcasts.length === 0 ? (
            <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
              <Radio className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <p className="text-xl text-gray-400 mb-2">
                {search ? 'No matching podcasts' : 'No podcasts on this platform'}
              </p>
              <p className="text-gray-500">
                {search ? 'Try a different search term' : 'Add a podcast using the button above'}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredPodcasts.map((podcast) => (
                <div
                  key={podcast.pid}
                  onClick={() => navigate(`/podcasts/${podcast.pid}/episodes`)}
                  className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors cursor-pointer"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0">
                      <PodcastImage url={podcast.cover_url} alt={podcast.title} />

                      <div className="flex-1 min-w-0">
                        <h3 className="text-base md:text-lg font-semibold text-white mb-1 line-clamp-2">
                          {podcast.title}
                        </h3>
                        {podcast.author && (
                          <p className="text-sm text-gray-400 mb-1 md:mb-2">{podcast.author}</p>
                        )}
                        <p className="text-sm text-gray-500 line-clamp-2 hidden sm:block">
                          {podcast.description || 'No description'}
                        </p>
                        <p className="text-sm text-indigo-400 mt-1 md:mt-2">
                          {podcast.summarized_count > 0
                            ? `${podcast.summarized_count} / ${podcast.episode_count} summarized`
                            : `${podcast.episode_count} episodes`
                          }
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 justify-end sm:justify-start" onClick={e => e.stopPropagation()}>
                      <Link
                        to={`/podcasts/${podcast.pid}/episodes`}
                        className="flex items-center gap-1 px-3 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors text-sm"
                      >
                        <ExternalLink size={16} />
                        <span className="hidden sm:inline">Episodes</span>
                      </Link>
                      {podcast.platform !== 'local' && (
                        <button
                          onClick={() => handleRefresh(podcast.pid)}
                          disabled={refreshing === podcast.pid}
                          className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                          title="Refresh episodes"
                        >
                          <RefreshCw size={16} className={refreshing === podcast.pid ? 'animate-spin' : ''} />
                        </button>
                      )}
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
        </>
      )}
    </div>
  )
}

function PodcastImage({ url, alt }: { url?: string; alt: string }) {
  const [error, setError] = useState(false)

  if (!url || error) {
    return (
      <div className="w-14 h-14 md:w-20 md:h-20 rounded-lg bg-dark-hover flex items-center justify-center flex-shrink-0">
        <Radio className="w-6 h-6 md:w-8 md:h-8 text-gray-600" />
      </div>
    )
  }

  const proxyUrl = `/api/image-proxy?url=${encodeURIComponent(url)}`

  return (
    <img
      src={proxyUrl}
      alt={alt}
      className="w-14 h-14 md:w-20 md:h-20 rounded-lg object-cover bg-dark-hover flex-shrink-0"
      onError={() => setError(true)}
    />
  )
}
