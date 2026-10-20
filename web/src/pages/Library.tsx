import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchSummaries, fetchVideoTasks } from '../lib/api'
import { getCache, setCache } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { prefetchSummary, prefetchVideoNote } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'
import { useReadingPosition } from '../lib/reading'
import { FileText, Headphones, Video, ArrowUpRight, RefreshCw, Search, LayoutGrid, List } from 'lucide-react'
import { useRef } from 'react'
import LoadError from '../components/LoadError'

type Item = { id: string; kind: 'podcast' | 'video'; title: string; source: string; href: string; date: string; status: string }
export default function Library() {
  const [items, setItems] = useState<Item[]>(() => getCache('library') || [])
  const [loading, setLoading] = useState(() => !getCache('library'))
  const request = useRef(0)
  const [layout, setLayout] = useState<'grid' | 'list'>('grid')
  const [limit, setLimit] = useState(60)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  usePageTiming('library', !loading, 'library', !!error)
  const [params, setParams] = useSearchParams()
  useReadingPosition('library', undefined, !loading)
  const source = params.get('source') || ''
  const query = params.get('q') || ''; const kind = params.get('kind') || ''; const status = params.get('status') || ''
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); setParams(next, { replace: true }) }
  async function load() {
    const owner = getAccountId(); const attempt = ++request.current
    setError(''); setRefreshing(true)
    const current = () => owner === getAccountId() && attempt === request.current
    const accept = (kind: Item['kind'], rows: Item[]) => {
      if (!current()) return
      setItems(previous => {
        const next = [...previous.filter(item => item.kind !== kind), ...rows].sort((a, b) => b.date.localeCompare(a.date))
        setCache('library', next, owner)
        return next
      })
      setLoading(false)
    }
    const results = await Promise.allSettled([
      fetchSummaries().then(summaries => accept('podcast', summaries.map(s => ({ id: s.episode_id, kind: 'podcast', title: s.title, source: s.podcast_title || 'Podcast', href: `/viewer/${s.episode_id}`, date: s.created_at || '', status: 'completed' })))),
      fetchVideoTasks().then(videos => accept('video', videos.tasks.filter(t => t.status !== 'discovered').map(t => ({ id: t.id, kind: 'video', title: t.title || 'Untitled video', source: t.channel || t.platform, href: `/videos/${t.id}`, date: t.updated_at || t.created_at || '', status: t.status === 'success' ? 'completed' : t.status })))),
    ])
    if (!current()) return
    const failed = results.flatMap((r, i) => r.status === 'rejected' ? [i === 0 ? 'podcasts' : 'videos'] : [])
    if (failed.length) setError(`Could not refresh ${failed.join(' and ')}. Previously loaded notes are still available.`)
    setLoading(false); setRefreshing(false)
  }
  useEffect(() => { void load(); return () => { request.current++ } }, [])
  useEffect(() => setLimit(60), [query, kind, status, source])
  const shown = useMemo(() => items.filter(i => (!source || i.source === source) && (!kind || i.kind === kind) && (!status || i.status === status) && `${i.title} ${i.source}`.toLowerCase().includes(query.toLowerCase())), [items, query, kind, status, source])
  return <div className="space-y-5 w-full library-workspace">
    <header className="flex flex-wrap gap-4 items-center justify-between"><div><div className="flex items-center gap-2 text-indigo-300 text-sm mb-1"><FileText size={16} /> YOUR NOTES</div><h1 className="text-3xl font-semibold tracking-tight">Library</h1><p className="text-gray-400 mt-1">Your summaries, ready to pick up where you left off.</p></div><button disabled={refreshing} onClick={() => void load()} className="inline-flex items-center gap-2 px-4 py-2.5 bg-dark-surface border border-dark-border rounded-lg disabled:opacity-60"><RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />{refreshing ? 'Refreshing…' : 'Refresh library'}</button></header>
    {error && <LoadError message={error} onRetry={() => void load()} />}
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_auto_auto_auto] gap-3">
      <input aria-label="Search saved notes" placeholder="Search title, podcast or channel…" value={query} onChange={e => update('q', e.target.value)} className="min-w-0 flex-1 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg" />
      <select aria-label="Podcast or channel" value={source} onChange={e => update('source', e.target.value)} className="min-w-0 sm:max-w-52 px-3 py-3 bg-dark-surface rounded-lg"><option value="">All sources</option>{Array.from(new Set(items.map(i => i.source))).sort().map(s => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Media type" value={kind} onChange={e => update('kind', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All media</option><option value="podcast">Podcasts</option><option value="video">Videos</option></select>
      <select aria-label="Note status" value={status} onChange={e => update('status', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Needs attention</option><option value="pending">Queued</option><option value="summarizing">Summarizing</option><option value="transcribing">Transcribing</option><option value="downloading">Downloading</option><option value="cancelled">Cancelled</option></select>
    </div>
    <div className="flex items-center justify-between gap-3"><p role="status" className="text-sm text-gray-400">{loading ? 'Loading your notes…' : `${shown.length} notes`}{refreshing && !loading ? ' · Updating sources…' : ''}</p><div className="flex gap-1 rounded-lg border border-dark-border p-1">{(['grid', 'list'] as const).map(mode => <button key={mode} aria-label={`${mode} layout`} aria-pressed={layout === mode} onClick={() => setLayout(mode)} className={`p-2 rounded ${layout === mode ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:bg-dark-hover'}`}>{mode === 'grid' ? <LayoutGrid size={16} /> : <List size={16} />}</button>)}</div></div>
    {(loading || (refreshing && items.length === 0)) && <div aria-hidden className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">{Array.from({length:8}, (_,i) => <div key={i} className="h-40 rounded-xl border border-dark-border bg-dark-surface animate-pulse" />)}</div>}
    <div className={layout === 'grid' ? 'grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4' : 'grid gap-2'}>{shown.slice(0, limit).map(i => <Link key={`${i.kind}:${i.id}`} to={i.href} onPointerEnter={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} onFocus={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} className={`group min-w-0 p-4 rounded-xl border border-dark-border bg-dark-surface hover:border-indigo-400 hover:bg-slate-800 transition-colors ${layout === 'list' ? 'flex items-center gap-4' : 'flex flex-col gap-4'}`}>
      <div className="flex items-center gap-2 text-xs text-indigo-300">{i.kind === 'podcast' ? <Headphones size={18} /> : <Video size={18} />}<span className={layout === 'list' ? 'hidden sm:inline' : ''}>{i.kind === 'podcast' ? 'Podcast' : 'Video'}</span></div>
      <div className="min-w-0 flex-1"><h2 className="font-semibold leading-snug line-clamp-2 group-hover:text-indigo-200">{i.title}</h2><p className="mt-2 text-sm text-gray-400 truncate">{i.source}</p></div>
      <div className="flex items-center gap-3 justify-between text-xs text-gray-400"><span className={`rounded-md px-2 py-1 ${i.status === 'completed' ? 'bg-emerald-950 text-emerald-200' : i.status === 'failed' ? 'bg-red-950 text-red-200' : 'bg-dark-bg'}`}>{i.status === 'completed' ? 'Ready to read' : i.status.replace(/_/g, ' ')}</span><ArrowUpRight size={16} className="text-gray-400 group-hover:text-white" /></div>
    </Link>)}</div>
    {!loading && !refreshing && !error && shown.length === 0 && <div className="rounded-xl border border-dashed border-dark-border p-12 text-center"><Search size={28} className="mx-auto mb-3 text-indigo-300" /><h2 className="font-semibold">No matching notes</h2><p className="text-gray-400 mt-2">Try another search or add content from <Link className="underline" to="/podcasts">Podcasts</Link> or <Link className="underline" to="/videos">Videos</Link>.</p></div>}
    {shown.length > limit && <button className="block mx-auto px-6 py-3 rounded-lg bg-dark-surface border border-dark-border" onClick={() => setLimit(value => value + 60)}>Show more notes ({shown.length - limit} remaining)</button>}
  </div>
}
