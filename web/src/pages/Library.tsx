import { useWarmCache } from '../lib/cache'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getCache, setCache } from '../lib/cache'
import { getAccountId, getPreference, setPreference } from '../lib/preferences'
import { prefetchSummary, prefetchVideoNote, cancelPrefetch } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'
import { useReadingPosition } from '../lib/reading'
import { Headphones, Video, ArrowUpRight, RefreshCw, Search, LayoutGrid, List } from 'lucide-react'
import { useRef } from 'react'
import LoadError from '../components/LoadError'

import type { LibraryItem as Item, LibraryPage } from '../lib/api'
import { fetchLibrary } from '../lib/api'
export default function Library() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''; const kind = params.get('kind') || ''; const status = params.get('status') || ''; const source = params.get('source') || ''; const sort = params.get('sort') || 'newest'
  const filterKey = new URLSearchParams({q:query,kind,status,source,sort}).toString()
  const cacheKey = 'library_page:' + filterKey
  const [loadedFilter, setLoadedFilter] = useState(filterKey)
  const [items, setItems] = useState<Item[]>(() => getCache<LibraryPage>(cacheKey)?.items || [])
  const [cursor, setCursor] = useState<string | null>(() => getCache<LibraryPage>(cacheKey)?.next_cursor || null)
  const [loading, setLoading] = useState(() => !getCache(cacheKey))
  const request = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const [layout, setLayout] = useState<'grid' | 'list'>(() => getPreference('library_layout') === 'list' ? 'list' : 'grid')
  const [refreshing, setRefreshing] = useState(false)
  useWarmCache<LibraryPage>(cacheKey, value => {setItems(value.items);setCursor(value.next_cursor);setLoadedFilter(filterKey);setLoading(false)})
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [error, setError] = useState('')
  usePageTiming('library', !loading && loadedFilter === filterKey, cacheKey, !!error)
  useReadingPosition('library:' + filterKey, undefined, !loading && loadedFilter === filterKey)
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); setParams(next, { replace: true }) }
  async function load(nextCursor = '') {
    const owner = getAccountId(); const attempt = ++request.current
    controller.current?.abort(); controller.current = new AbortController()
    setError(''); setRefreshing(true)
    try {
      const result = await fetchLibrary(filterKey, nextCursor, controller.current.signal)
      if (owner !== getAccountId() || attempt !== request.current) return
      setItems(previous => {
        const next = nextCursor ? [...previous, ...result.items.filter(row => !previous.some(old => old.kind === row.kind && old.id === row.id))] : result.items
        setCache(cacheKey, {...result,items:next,cachedAt:Date.now()}, owner)
        return next
      })
      setLoadedFilter(filterKey)
      setCursor(result.next_cursor)
    } catch (e) {
      if (owner === getAccountId() && attempt === request.current) setError(e instanceof Error ? e.message : 'Could not load notes')
    } finally {
      if (owner === getAccountId() && attempt === request.current) { setLoading(false); setRefreshing(false) }
    }
  }
  useEffect(() => {
    const cached = getCache<LibraryPage & {cachedAt?:number}>(cacheKey)
    setError('')
    if(cached){setItems(cached.items);setCursor(cached.next_cursor);setLoadedFilter(filterKey);setLoading(false);setRefreshing(false)}
    else {setCursor(null);setRefreshing(true)}
    const timer = cached && Date.now() - (cached.cachedAt || 0) < 60000 ? undefined : setTimeout(() => void load(), query || source ? 250 : 0)
    return () => { clearTimeout(timer); request.current++; controller.current?.abort() }
  }, [filterKey])
  const shown = items
  return <div className="workspace-page space-y-5 w-full library-workspace">
    <header className="flex flex-wrap gap-4 items-center justify-between"><div className="min-w-0 flex-1"><h1 className="page-title text-3xl font-semibold tracking-tight">Library</h1><p className="text-gray-400 mt-1">Your summaries, ready to pick up where you left off.</p></div><button aria-label={refreshing ? "Refreshing library" : "Refresh library"} disabled={refreshing} onClick={() => void load()} className="inline-flex items-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border rounded-lg disabled:opacity-60"><RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} /><span className="hidden sm:inline">{refreshing ? 'Refreshing…' : 'Refresh library'}</span></button></header>
    {loadedFilter!==filterKey && !refreshing && <p role="status" className="text-sm text-gray-400">Showing previous results. Retry to apply your new filters.</p>}
    {error && <LoadError message={error} onRetry={() => void load()} />}
    <div className="library-filters">
      <input aria-label="Search saved notes" placeholder="Search title, podcast or channel…" value={query} onChange={e => update('q', e.target.value)} className="min-w-0 flex-1 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg" />
      <button className="library-filter-toggle border border-dark-border px-3" aria-expanded={filtersOpen} aria-controls="library-filter-options" onClick={() => setFiltersOpen(open => !open)}>Filters{kind || status || source ? ' · Active' : ''}</button>
      <div id="library-filter-options" className="library-filter-options" data-expanded={filtersOpen}>
      <input aria-label="Podcast or channel" placeholder="Filter podcast or channel…" value={source} onChange={e => update('source', e.target.value)} className="min-w-0 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg" />
      <select aria-label="Media type" value={kind} onChange={e => update('kind', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All media</option><option value="podcast">Podcasts</option><option value="video">Videos</option></select>
      <select aria-label="Note status" value={status} onChange={e => update('status', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Needs attention</option><option value="pending">Queued</option><option value="summarizing">Summarizing</option><option value="transcribing">Transcribing</option><option value="downloading">Downloading</option><option value="cancelled">Cancelled</option></select>
    </div></div>
    <div className="library-results-bar"><p role="status" className="text-sm text-gray-400">{loading ? 'Loading your notes…' : `${shown.length} notes loaded${cursor ? " · More available" : ""}`}{refreshing && !loading ? loadedFilter !== filterKey ? ' · Searching…' : ' · Updating…' : ''}</p><select aria-label="Sort notes" value={sort} onChange={e => update('sort', e.target.value)} className="p-2 rounded bg-dark-surface"><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select><div className="flex gap-1 rounded-lg border border-dark-border p-1">{(['grid', 'list'] as const).map(mode => <button key={mode} aria-label={`${mode} layout`} aria-pressed={layout === mode} onClick={() => { setLayout(mode); setPreference('library_layout', mode) }} className={`p-2 rounded ${layout === mode ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-dark-hover'}`}>{mode === 'grid' ? <LayoutGrid size={16} /> : <List size={16} />}</button>)}</div></div>
    {(query || kind || status || source || sort !== 'newest') && <button onClick={() => setParams({}, { replace: true })} className="text-sm text-indigo-300 underline">Clear filters</button>}
    {(loading || (refreshing && items.length === 0)) && <div aria-hidden className="collection-grid">{Array.from({length:8}, (_,i) => <div key={i} className="h-40 rounded-xl border border-dark-border bg-dark-surface animate-pulse" />)}</div>}
    <div className={layout === 'grid' ? 'collection-grid' : 'grid gap-2'}>{shown.map(i => <Link key={`${i.kind}:${i.id}`} to={i.kind === 'podcast' ? `/viewer/${i.id}` : `/videos/${i.id}`} onPointerEnter={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} onPointerLeave={() => cancelPrefetch()} onBlur={() => cancelPrefetch()} onFocus={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} className={`library-card group min-w-0 p-4 rounded-xl border border-dark-border bg-dark-surface hover:border-indigo-400 hover:bg-slate-800 transition-colors ${layout === 'list' ? 'flex items-center gap-4' : 'flex flex-col gap-4'}`}>
      <div className="flex items-center gap-2 text-xs text-indigo-300">{i.kind === 'podcast' ? <Headphones size={18} /> : <Video size={18} />}<span className={layout === 'list' ? 'hidden sm:inline' : ''}>{i.kind === 'podcast' ? 'Podcast' : 'Video'}</span></div>
      <div className="min-w-0 flex-1"><h2 className="font-semibold leading-snug line-clamp-2 group-hover:text-indigo-200">{i.title}</h2><p className="mt-2 text-sm text-gray-400 truncate">{i.source}</p><time className="text-xs text-gray-500" dateTime={i.date}>{i.date ? new Date(i.date).toLocaleDateString() : ""}</time></div>
      <div className="flex items-center gap-3 justify-between text-xs text-gray-400"><span className={`rounded-md px-2 py-1 ${i.status === 'completed' ? 'bg-emerald-950 text-emerald-200' : i.status === 'failed' ? 'bg-red-950 text-red-200' : 'bg-dark-bg'}`}>{i.status === 'completed' ? 'Ready to read' : i.status.replace(/_/g, ' ')}</span><ArrowUpRight size={16} className="text-gray-400 group-hover:text-white" /></div>
    </Link>)}</div>
    {!loading && !refreshing && !error && shown.length === 0 && <div className="rounded-xl border border-dashed border-dark-border p-12 text-center"><Search size={28} className="mx-auto mb-3 text-indigo-300" /><h2 className="font-semibold">No matching notes</h2><p className="text-gray-400 mt-2">Try another search or add content from <Link className="underline" to="/podcasts">Podcasts</Link> or <Link className="underline" to="/videos">Videos</Link>.</p></div>}
    {cursor && loadedFilter === filterKey && <button disabled={refreshing} className="block mx-auto px-6 py-3 rounded-lg bg-dark-surface border border-dark-border disabled:opacity-50" onClick={() => void load(cursor)}>{refreshing ? 'Loading more…' : 'Show more notes'}</button>}
  </div>
}
