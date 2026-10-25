import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import CachedImage from '../components/CachedImage'
import { useWarmCache } from '../lib/cache'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getCache, setCache } from '../lib/cache'
import { getAccountId, getPreference, setPreference } from '../lib/preferences'
import { prefetchSummary, prefetchVideoNote, cancelPrefetch } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'
import { useReadingPosition } from '../lib/reading'
import {useReadingHistory} from '../lib/readingHistory'
import { Headphones, Video, FileText, ArrowUpRight, RefreshCw, Search, LayoutGrid, List } from 'lucide-react'
import { useRef } from 'react'
import LoadError from '../components/LoadError'
import { platformLabel } from '../lib/platformLabels'

import type { LibraryItem as Item, LibraryPage } from '../lib/api'
import { fetchLibrary, fetchLibrarySources } from '../lib/api'
export default function Library() {
  const history=useReadingHistory()
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''; const kind = params.get('kind') || ''; const status = 'completed'; const source = params.get('source') || ''; const sort = params.get('sort') || 'newest'
  const filterKey = new URLSearchParams({q:query,kind,status,source,sort}).toString()
  const cacheKey = 'library_page:v6:' + filterKey
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
  const [sources, setSources] = useState<string[]>([])
  const [sourcesError, setSourcesError] = useState(false)
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [sourceAttempt, setSourceAttempt] = useState(0)
  useEffect(() => {
    if (loading) return
    const abort = new AbortController(); const owner = getAccountId()
    const catalog: string[] = []; const cursors = new Set<string>()
    let active = true
    setSourcesError(false); setSourcesLoading(true)
    void (async () => {
      let cursor = ''
      do {
        const page = await fetchLibrarySources(cursor, abort.signal)
        if (!active || owner !== getAccountId()) return
        catalog.push(...page.sources)
        setSources([...new Set(catalog)])
        if (!page.next_cursor) return
        if (cursors.has(page.next_cursor)) throw new Error('Source cursor did not advance')
        cursor = page.next_cursor; cursors.add(cursor)
      } while (active)
    })().catch(() => { if (active && owner === getAccountId()) setSourcesError(true) })
      .finally(() => { if (active && owner === getAccountId()) setSourcesLoading(false) })
    return () => { active = false; abort.abort() }
  }, [loading, sourceAttempt])
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
  const shown = items.filter(item => item.status === 'completed')
  return <div className="workspace-page space-y-5 w-full library-workspace">
    <header className="flex flex-wrap gap-4 items-center justify-between"><div className="min-w-0 flex-1"><h1 className="page-title text-3xl font-semibold tracking-tight">Library</h1><p className="text-gray-400 mt-1">Your summaries, ready to pick up where you left off.</p></div><Button aria-label={refreshing ? "Refreshing library" : "Refresh library"} disabled={refreshing} onClick={() => void load()} className="inline-flex items-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border rounded-lg disabled:opacity-60"><RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} /><span className="hidden sm:inline">{refreshing ? 'Refreshing…' : 'Refresh library'}</span></Button></header>
    {loadedFilter!==filterKey && !refreshing && <p role="status" className="text-sm text-gray-400">Showing previous results. Retry to apply your new filters.</p>}
    {error && <LoadError message={error} onRetry={() => void load()} />}
    <div className="library-filters">
      <input aria-label="Search saved notes" placeholder="Search title, podcast or channel…" value={query} onChange={e => update('q', e.target.value)} className="min-w-0 flex-1 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg" />
      <button className="library-filter-toggle border border-dark-border px-3" aria-expanded={filtersOpen} aria-controls="library-filter-options" onClick={() => setFiltersOpen(open => !open)}>Filters{kind || source ? ' · Active' : ''}</button>
      <div id="library-filter-options" className="library-filter-options" data-expanded={filtersOpen}>
      <select aria-label="Podcast or channel" aria-describedby={sourcesLoading || sourcesError ? 'library-source-status' : undefined} value={source} onChange={e=>update("source",e.target.value)} className="min-w-0 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg"><option value="">All sources</option>{Array.from(new Set([source,...sources,...items.map(i=>i.source)])).filter(Boolean).sort().map(value=><option key={value} value={value}>{value}</option>)}</select>
      <select aria-label="Media type" value={kind} onChange={e => update('kind', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All media</option><option value="podcast">Podcasts</option><option value="video">Video & audio</option><option value="article">Articles & text</option></select>

    </div></div>
    {sourcesLoading && <p id="library-source-status" role="status" className="text-sm text-gray-400">Loading sources…</p>}
    {!sourcesLoading && sourcesError && <p id="library-source-status" role="status" className="text-sm text-gray-400">Source list could not finish loading. <button className="text-indigo-300 underline" onClick={() => setSourceAttempt(value => value + 1)}>Retry sources</button></p>}
    <div className="library-results-bar"><p role="status" className="text-sm text-gray-400">{loading ? 'Loading your notes…' : `${shown.length} notes loaded${cursor ? " · More available" : ""}`}{refreshing && !loading ? loadedFilter !== filterKey ? ' · Searching…' : ' · Updating…' : ''}</p><select aria-label="Sort notes" value={sort} onChange={e => update('sort', e.target.value)} className="p-2 rounded bg-dark-surface"><option value="newest">Recently saved</option><option value="oldest">Earliest saved</option><option value="published">Recently published</option></select><div className="flex gap-1 rounded-lg border border-dark-border p-1">{(['grid', 'list'] as const).map(mode => <button key={mode} aria-label={`${mode} layout`} aria-pressed={layout === mode} onClick={() => { setLayout(mode); setPreference('library_layout', mode) }} className={`p-2 rounded ${layout === mode ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-dark-hover'}`}>{mode === 'grid' ? <LayoutGrid size={16} /> : <List size={16} />}</button>)}</div></div>
    {(query || kind || source || sort !== 'newest') && <button onClick={() => setParams({}, { replace: true })} className="text-sm text-indigo-300 underline">Clear filters</button>}
    {(loading || (refreshing && items.length === 0)) && <div aria-hidden className="collection-grid">{Array.from({length:8}, (_,i) => <div key={i} className="h-40 rounded-xl border border-dark-border bg-dark-surface animate-pulse" />)}</div>}
    <div className={layout === 'grid' ? 'collection-grid' : 'grid gap-3'}>{shown.map((i,index) => <Link key={`${i.kind}:${i.id}`} to={i.kind === 'podcast' ? `/viewer/${i.id}` : `/videos/${i.id}`} onPointerEnter={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} onPointerLeave={cancelPrefetch} onBlur={cancelPrefetch} onFocus={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} className="library-card group" data-layout={layout} data-kind={i.kind}>
      <LibraryArtwork priority={index<4} key={`${i.kind}:${i.id}:${i.thumbnail || ''}`} item={i} />
      <div className="library-card-body">
        <div className="library-card-meta"><span>{platformLabel(i.platform,i.kind === 'podcast' ? 'Podcast' : 'Video')}</span><time title={i.published_at ? `Published ${i.published_at.slice(0,10)}` : "Date this summary was saved, not its original publication date"} dateTime={i.published_at || i.date}>{i.published_at ? `Published ${i.published_at.slice(0,10)}` : i.date ? `Saved ${new Date(i.date).toLocaleDateString()}` : ''}</time></div>
        <h2 className="font-semibold leading-snug line-clamp-2 group-hover:text-indigo-200">{i.title}</h2>
        <p className="mt-2 text-sm text-gray-400 truncate">{i.source}</p>
        <div className="library-card-footer"><span>{history.some(r=>r.kind===i.kind&&r.id===i.id) ? `${history.find(r=>r.kind===i.kind&&r.id===i.id)!.progress}% read` : i.topics_count ? `${i.topics_count} topics` : 'Ready to read'}</span><span className="flex items-center gap-1">{i.content_type==='article'?'Read article':['twitter','substack'].includes(i.platform||'')?'Read post':'Read summary'} <ArrowUpRight size={14} /></span></div>
      </div>
    </Link>)}</div>
    {!loading && !refreshing && !error && shown.length === 0 && <EmptyState title="No matching notes"><Search size={28} className="mx-auto mb-3 text-indigo-300" /><p className="text-gray-400 mt-2">Try another search or add content from <Link className="underline" to="/podcasts">Podcasts</Link> or <Link className="underline" to="/videos">Videos</Link>.</p></EmptyState>}
    {cursor && loadedFilter === filterKey && <button disabled={refreshing} className="block mx-auto px-6 py-3 rounded-lg bg-dark-surface border border-dark-border disabled:opacity-50" onClick={() => void load(cursor)}>{refreshing ? 'Loading more…' : 'Show more notes'}</button>}
  </div>
}

function LibraryArtwork({item,priority}: {item: Item;priority:boolean}) {
  const audio = item.kind === 'podcast' || item.content_type === 'audio'
  const Icon = audio ? Headphones : item.content_type==='article' ? FileText : Video
  const minutes = Math.floor((item.duration || 0) / 60)
  return <div className="library-artwork" aria-hidden="true">
    <CachedImage priority={priority} src={item.thumbnail || ''} alt="" className="library-cover-image" fit={item.kind === 'podcast' ? 'contain' : 'cover'} fallback={<div className="library-artwork-fallback"><Icon size={36} strokeWidth={1.5}/><span>{item.source.slice(0, 24)}</span></div>} />
    <span className="library-media-badge"><Icon size={13}/>{audio ? 'Audio' : item.content_type==='article' ? 'Article' : 'Video'}</span>
    {minutes > 0 && <span className="library-duration">{minutes} min</span>}
  </div>
}
