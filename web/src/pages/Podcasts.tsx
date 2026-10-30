import {OptionalTool} from '../components/DeferredView'
const PodcastUploadForm=lazy(()=>import('../components/PodcastUploadForm'))
import CachedImage from '../components/CachedImage'
import LoadError from '../components/LoadError'
import { lazy, useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link, useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { Radio, Plus, Trash2, RefreshCw, Loader2, ExternalLink, ArrowLeft, ChevronRight, Search, Upload } from 'lucide-react'
import { fetchPodcasts, addPodcast, removePodcast, refreshPodcast, uploadLocalPodcastAudio, type Podcast } from '../lib/api'
import { useToast } from '../components/Toast'
import PlatformIcon, { PLATFORM_COLORS } from '../components/PlatformIcon'
import { useWarmCache, getCache, setCache, CacheKeys } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { prefetchEpisodes, cancelPrefetch } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'
import { detectPodcastPlatform } from '../lib/contentLinks'

const PODCAST_PLATFORMS: { id: string; label: string }[] = [
  { id: 'xiaoyuzhou', label: '小宇宙' },
  { id: 'apple', label: 'Apple Podcasts' },
  { id: 'spotify', label: 'Spotify' },
  { id: 'local', label: 'Local Uploads' },
]

const PLATFORM_LABELS: Record<string, string> = {
  xiaoyuzhou: '小宇宙',
  apple: 'Apple Podcasts',
  spotify: 'Spotify',
  local: 'Local Uploads',
}

type View =
  | { type: 'platforms' }
  | { type: 'podcasts'; platform: string }

function detectPlatform(url: string): string {
  return detectPodcastPlatform(url)
}

export default function Podcasts() {
  const [podcasts, setPodcasts] = useState<Podcast[]>(() => getCache(CacheKeys.PODCASTS) || [])
  const [loading, setLoading] = useState(() => !getCache(CacheKeys.PODCASTS))
  usePageTiming('podcasts', !loading, CacheKeys.PODCASTS)
  useWarmCache<Podcast[]>(CacheKeys.PODCASTS,value=>{setPodcasts(value);setLoading(false)})
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const [adding, setAdding] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [showUploadForm, setShowUploadForm] = useState(false)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [pendingActions, setPendingActions] = useState<Record<string, 'refresh' | 'delete'>>({})
  const actionLocks = useRef(new Set<string>())
  const bulkLock = useRef(false)
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const currentRoute = useRef<string | null>(location.key)
  currentRoute.current = location.key
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
    setSearchParams(params)
  }, [setSearchParams])

  const listRequest = useRef(0)
  useEffect(() => { currentRoute.current = location.key; loadPodcasts(); return () => { listRequest.current++; currentRoute.current = null } }, [])

  function changePodcasts(change: (rows: Podcast[]) => Podcast[]) {
    const owner = getAccountId()
    listRequest.current++
    setError('')
    setPodcasts(previous => {
      const next = change(previous)
      setCache(CacheKeys.PODCASTS, next, owner)
      return next
    })
  }

  async function loadPodcasts() {
    const owner = getAccountId()
    const request = ++listRequest.current
    setError('')
    try {
      const data = await fetchPodcasts()
      if (owner !== getAccountId() || request !== listRequest.current) return
      setPodcasts(data)
      setCache(CacheKeys.PODCASTS, data, owner)
    } catch (err) {
      if (owner !== getAccountId() || request !== listRequest.current) return
      console.error('Failed to load podcasts:', err)
      setError('Cannot load your podcasts. Check the connection and retry.')
    } finally {
      if (owner === getAccountId() && request === listRequest.current) setLoading(false)
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
    if (submitting.current || !newUrl.trim()) return

    const routeKey = location.key
    submitting.current = true
    setAdding(true)
    const toastId = addToast({
      type: 'loading',
      title: 'Adding podcast...',
      message: 'Fetching podcast information',
    })

    try {
      const podcast = await addPodcast(newUrl)
      changePodcasts(prev => [podcast, ...prev.filter(item => item.pid !== podcast.pid)])
      setNewUrl('')
      setShowAddForm(false)
      removeToast(toastId)
      addToast({ type: 'success', title: podcast.resolved_episode_id ? 'Spotify episode matched to public RSS' : 'Podcast added', message: podcast.resolved_episode_title || podcast.title })
      if (podcast.resolved_episode_id && currentRoute.current === routeKey) navigate(`/podcasts/${podcast.pid}/episodes`)
    } catch (err: unknown) {
      removeToast(toastId)
      addToast({
        type: 'error',
        title: 'Failed to add podcast',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      submitting.current = false
      setAdding(false)
    }
  }

  async function handleUploadAudio(e: React.FormEvent) {
    e.preventDefault()
    if (submitting.current || !audioFile) return

    const routeKey = location.key
    submitting.current = true
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
      if (currentRoute.current === routeKey) navigate(`/podcasts/${result.podcast.pid}/episodes`)
    } catch (err: unknown) {
      removeToast(toastId)
      addToast({
        type: 'error',
        title: 'Upload failed',
        message: err instanceof Error ? err.message : 'Unknown error',
      })
    } finally {
      submitting.current = false
      setUploading(false)
    }
  }

  function beginAction(pid: string, action: 'refresh' | 'delete') {
    if (bulkLock.current || actionLocks.current.has(pid)) return false
    actionLocks.current.add(pid)
    setPendingActions(previous => ({...previous, [pid]: action}))
    return true
  }
  function finishAction(pid: string) {
    actionLocks.current.delete(pid)
    setPendingActions(previous => { const next = {...previous}; delete next[pid]; return next })
  }

  async function handleRemove(pid: string) {
    if (bulkLock.current || actionLocks.current.has(pid)) return
    if (!confirm('Remove this podcast?') || !beginAction(pid, 'delete')) return
    const podcast = podcasts.find(p => p.pid === pid)
    try {
      await removePodcast(pid)
      changePodcasts(prev => prev.filter(p => p.pid !== pid))
      addToast({ type: 'success', title: 'Podcast removed', message: podcast?.title || '' })
    } catch (err) {
      addToast({ type: 'error', title: 'Failed to remove podcast', message: err instanceof Error ? err.message : undefined })
    } finally {
      finishAction(pid)
    }
  }

  async function handleRefresh(pid: string) {
    const podcast = podcasts.find(p => p.pid === pid)
    if ((podcast?.platform || 'xiaoyuzhou') === 'local') {
      addToast({ type: 'info', title: 'Local uploads', message: 'Uploaded audio is managed manually and does not support refresh.' })
      return
    }
    if (!beginAction(pid, 'refresh')) return
    try {
      const result = await refreshPodcast(pid)
      addToast({ type: 'success', title: 'Podcast refreshed', message: result.message })
      loadPodcasts()
    } catch (error) {
      addToast({ type: 'error', title: 'Failed to refresh podcast', message: error instanceof Error ? error.message : 'Source unavailable' })
    } finally {
      finishAction(pid)
    }
  }

  async function handleCheckAllUpdates() {
    if (bulkLock.current || actionLocks.current.size) return
    if (view.type === 'podcasts' && view.platform === 'local') {
      addToast({ type: 'info', title: 'Local uploads', message: 'Local uploads do not have external updates to check.' })
      return
    }
    const platformPodcasts = podcasts.filter(p => p.platform !== 'local' && (view.type !== 'podcasts' || (p.platform || 'xiaoyuzhou') === view.platform))
    if (platformPodcasts.length === 0) {
      addToast({type:'info',title:'No update sources',message:'Add a public podcast subscription to check for new episodes.'})
      return
    }

    bulkLock.current = true
    setRefreshingAll(true)
    let totalNew = 0
    let checked = 0
    const failures: string[] = []

    const owner = getAccountId()
    for (let offset=0;offset<platformPodcasts.length;offset+=3) {
      if (owner !== getAccountId()) { bulkLock.current = false; setRefreshingAll(false); return }
      await Promise.all(platformPodcasts.slice(offset,offset+3).map(async podcast => {
      try {
        const result = await refreshPodcast(podcast.pid)
        const match = result.message?.match(/(\d+)/)
        totalNew += result.new_episodes ?? (match ? parseInt(match[1],10) : 0)
        checked++
      } catch (error) {
        failures.push(`${podcast.title}: ${error instanceof Error ? error.message : 'Source unavailable'}`)
      }
      }))
    }

    bulkLock.current = false
    setRefreshingAll(false)
    if (owner !== getAccountId()) return
    loadPodcasts()
    addToast({
      type: failures.length ? 'error' : 'success',
      title: failures.length ? 'Update check incomplete' : 'Check complete',
      message: failures.length ? `${checked} checked; ${failures.length} unavailable. ${totalNew} new episodes kept. ${failures[0]}` : totalNew > 0
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
    const order = ['xiaoyuzhou', 'apple', 'spotify', 'local']
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

  if (error && !podcasts.length) return <LoadError message={error} onRetry={() => { void loadPodcasts() }} />

  return (
    <div className="workspace-page space-y-6">
      {error && <LoadError message={error} onRetry={() => { void loadPodcasts() }} />}
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {view.type === 'podcasts' && (
            <button
              aria-label="Back to podcast platforms"
                onClick={() => setView({ type: 'platforms' })}
              className="p-2 bg-dark-surface border border-dark-border rounded-lg hover:bg-dark-hover transition-colors flex-shrink-0"
            >
              <ArrowLeft size={20} />
            </button>
          )}
          <div>
            <h1 className="page-title text-xl md:text-2xl font-bold text-white mb-1 md:mb-2">
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
        <div className="podcast-source-actions flex items-center gap-2 w-full sm:w-auto">
          {(view.type !== 'podcasts' || view.platform !== 'local') && (
            <button
              onClick={handleCheckAllUpdates}
              aria-label="Check podcast updates"
              disabled={refreshingAll || Object.keys(pendingActions).length > 0}
              className="flex items-center justify-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border hover:bg-dark-hover text-white font-medium rounded-lg transition-colors disabled:opacity-50 flex-1 sm:flex-none"
              title="Check all podcasts for new episodes"
            >
              <RefreshCw size={18} className={refreshingAll ? 'animate-spin' : ''} />
              <span>{refreshingAll ? 'Checking…' : 'Check Updates'}</span>
            </button>
          )}
          <button
            disabled={adding || uploading}
            aria-expanded={showUploadForm}
            onClick={() => { setShowUploadForm(!showUploadForm); setShowAddForm(false) }}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border hover:bg-dark-hover text-white font-medium rounded-lg transition-colors disabled:opacity-50 flex-1 sm:flex-none"
          >
            <Upload size={18} />
            Upload Audio
          </button>
          <button
            disabled={adding || uploading}
            aria-expanded={showAddForm}
            onClick={() => { setShowAddForm(!showAddForm); setShowUploadForm(false) }}
            className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 flex-1 sm:flex-none"
          >
            <Plus size={20} />
            Add Podcast
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAddForm && (
        <div className="podcast-entry-panel p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Add New Podcast</h2>
          <form aria-busy={adding} onSubmit={handleAdd} className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-4">
            <div className="flex-1 relative">
              <input
                type="text"
                disabled={adding}
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                aria-label="Podcast URL"
                placeholder="Xiaoyuzhou, Apple Podcasts or Spotify episode URL…"
                className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
              />
              {detectedPlatform && (
                <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-gray-400">
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
          <p className="mt-3 text-sm text-gray-400">Spotify links import matching public RSS audio. Paid, exclusive or unmatched episodes may be unavailable.</p>
        </div>
      )}

      {showUploadForm && <OptionalTool fallback={<p role="status">Loading upload tools…</p>}>
        <PodcastUploadForm audioFile={audioFile} onFile={setAudioFile} title={uploadTitle} onTitle={setUploadTitle}
          description={uploadDescription} onDescription={setUploadDescription} uploading={uploading} onSubmit={handleUploadAudio}/>
      </OptionalTool>}

      {/* Search */}
      <div className="relative max-w-md">
        <Search size={16} className="absolute left-3 top-2.5 text-gray-500" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Search podcasts"
          placeholder="Search podcasts..."
          className="w-full pl-9 pr-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {/* Horizontal platform quick-select */}
      {sortedPlatforms.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            aria-label="Back to podcast platforms"
                onClick={() => setView({ type: 'platforms' })}
            className={`flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
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
                className={`flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-dark-surface border border-dark-border text-gray-400 hover:text-white hover:bg-dark-hover'
                }`}
              >
                <PlatformIcon platform={p} size={15} className={isActive ? 'text-white' : PLATFORM_COLORS[p] || 'text-gray-400'} />
                {label}
                <span className="text-xs">({count})</span>
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
            <div className="collection-grid">
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
              {filteredPodcasts.map((podcast,index) => (
                <div
                  key={podcast.pid}
                  onClick={() => navigate(`/podcasts/${podcast.pid}/episodes`)}
                  onPointerEnter={() => prefetchEpisodes(podcast.pid)}
                  onPointerLeave={cancelPrefetch}
                  onTouchStart={() => prefetchEpisodes(podcast.pid)}
                  className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl hover:border-dark-hover transition-colors cursor-pointer"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                    <div className="flex items-start gap-3 sm:gap-4 flex-1 min-w-0">
                      <PodcastImage priority={index<3} url={podcast.cover_url} alt={podcast.title} />

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
                        aria-label={`Open episodes: ${podcast.title}`}
                        onFocus={() => prefetchEpisodes(podcast.pid)}
                        onBlur={cancelPrefetch}
                        className="flex items-center gap-1 px-3 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors text-sm"
                      >
                        <ExternalLink size={16} />
                        <span className="hidden sm:inline">Episodes</span>
                      </Link>
                      {podcast.platform !== 'local' && (
                        <button
                          onClick={() => handleRefresh(podcast.pid)}
                          disabled={refreshingAll || !!pendingActions[podcast.pid]}
                          className="p-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
                          title="Refresh episodes"
                          aria-label={`Refresh ${podcast.title}`}
                          aria-busy={pendingActions[podcast.pid] === 'refresh'}
                        >
                          <RefreshCw size={16} className={pendingActions[podcast.pid] === 'refresh' ? 'animate-spin' : ''} />
                        </button>
                      )}
                      <button
                        onClick={() => handleRemove(podcast.pid)}
                        disabled={refreshingAll || !!pendingActions[podcast.pid]}
                        className="p-2 bg-dark-hover hover:bg-red-600/20 text-red-400 rounded-lg transition-colors disabled:opacity-50"
                        title="Remove podcast"
                        aria-label={`Remove ${podcast.title}`}
                        aria-busy={pendingActions[podcast.pid] === 'delete'}
                      >
                        {pendingActions[podcast.pid] === 'delete' ? (
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

function PodcastImage({ url, alt, priority=false }: { url?: string; alt: string; priority?:boolean }) {
  return <CachedImage priority={priority} src={url || ''} alt={alt} className="w-14 h-14 md:w-20 md:h-20 rounded-lg bg-dark-hover flex-shrink-0" fallback={<div className="cached-image-fallback"><Radio className="w-6 h-6 md:w-8 md:h-8 text-indigo-300" /></div>} />
}
