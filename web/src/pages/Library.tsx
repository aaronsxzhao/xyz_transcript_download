import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchSummaries, fetchVideoTasks } from '../lib/api'
import { getCache, setCache } from '../lib/cache'
import { getAccountId } from '../lib/preferences'
import { prefetchSummary, prefetchVideoNote } from '../lib/summaryPrefetch'
import { usePageTiming } from '../lib/pageTiming'
import { useReadingPosition } from '../lib/reading'
import LoadError from '../components/LoadError'

type Item = { id: string; kind: 'podcast' | 'video'; title: string; source: string; href: string; date: string; status: string }
export default function Library() {
  const [items, setItems] = useState<Item[]>(() => getCache('library') || [])
  const [loading, setLoading] = useState(() => !getCache('library'))
  const [error, setError] = useState('')
  usePageTiming('library', !loading, 'library', !!error)
  const [params, setParams] = useSearchParams()
  useReadingPosition('library', undefined, !loading)
  const source = params.get('source') || ''
  const query = params.get('q') || ''; const kind = params.get('kind') || ''; const status = params.get('status') || ''
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); value ? next.set(key, value) : next.delete(key); setParams(next, { replace: true }) }
  async function load() {
    const owner = getAccountId(); setError('')
    try {
      const [summaries, videos] = await Promise.all([fetchSummaries(), fetchVideoTasks()])
      if (owner !== getAccountId()) return
      const next: Item[] = [
        ...summaries.map(s => ({ id: s.episode_id, kind: 'podcast' as const, title: s.title, source: s.podcast_title || 'Podcast', href: `/viewer/${s.episode_id}`, date: s.created_at || '', status: 'completed' })),
        ...videos.tasks.filter(t => t.status !== 'discovered').map(t => ({ id: t.id, kind: 'video' as const, title: t.title || 'Untitled video', source: t.channel || t.platform, href: `/videos/${t.id}`, date: t.updated_at || t.created_at || '', status: t.status === 'success' ? 'completed' : t.status })),
      ].sort((a, b) => b.date.localeCompare(a.date))
      setItems(next); setCache('library', next, owner)
    } catch (e) { setError(e instanceof Error ? e.message : 'Cannot load your library') }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  const shown = useMemo(() => items.filter(i => (!source || i.source === source) && (!kind || i.kind === kind) && (!status || i.status === status) && `${i.title} ${i.source}`.toLowerCase().includes(query.toLowerCase())), [items, query, kind, status, source])
  return <div className="space-y-5 max-w-6xl mx-auto">
    <div className="flex flex-wrap gap-3 items-center justify-between"><div><h1 className="text-2xl font-bold">Library</h1><p className="text-gray-400">Find your podcast summaries and video notes in one place.</p></div><button onClick={() => void load()} className="px-4 py-2 bg-dark-surface border border-dark-border rounded-lg">Refresh library</button></div>
    {error && <LoadError message={error} onRetry={() => void load()} />}
    <div className="flex flex-col sm:flex-row gap-3">
      <input aria-label="Search saved notes" placeholder="Search title, podcast or channel…" value={query} onChange={e => update('q', e.target.value)} className="min-w-0 flex-1 px-3 py-3 bg-dark-surface border border-dark-border rounded-lg" />
      <select aria-label="Podcast or channel" value={source} onChange={e => update('source', e.target.value)} className="min-w-0 sm:max-w-52 px-3 py-3 bg-dark-surface rounded-lg"><option value="">All sources</option>{Array.from(new Set(items.map(i => i.source))).sort().map(s => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Media type" value={kind} onChange={e => update('kind', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All media</option><option value="podcast">Podcasts</option><option value="video">Videos</option></select>
      <select aria-label="Note status" value={status} onChange={e => update('status', e.target.value)} className="px-3 py-3 bg-dark-surface rounded-lg"><option value="">All statuses</option><option value="completed">Completed</option><option value="failed">Needs attention</option><option value="pending">Queued</option></select>
    </div>
    <p role="status" className="text-sm text-gray-400">{loading ? 'Loading library…' : `${shown.length} notes`}</p>
    <div className="grid md:grid-cols-2 gap-3">{shown.slice(0, 300).map(i => <Link key={`${i.kind}:${i.id}`} to={i.href} onPointerEnter={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} onFocus={() => i.kind === 'podcast' ? prefetchSummary(i.id) : prefetchVideoNote(i.id)} className="p-4 rounded-xl border border-dark-border bg-dark-surface hover:border-indigo-400"><h2 className="font-medium">{i.title}</h2><p className="mt-2 text-sm text-gray-400">{i.source} · {i.kind} · {i.status}</p></Link>)}</div>
    {!loading && !error && shown.length === 0 && <p>No matching notes. Try another search or add content from Podcasts or Videos.</p>}
    {shown.length > 300 && <p>Narrow your search to see more results.</p>}
  </div>
}
