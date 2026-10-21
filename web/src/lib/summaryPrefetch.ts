import { fetchSummary, fetchVideoTask, getReadRevision } from './api'
import { getAuthGeneration } from './auth'
import { CacheKeys, getCache, setCache } from './cache'
import { preloadPage } from './pages'
import { getAccountId } from './preferences'

const pending = new Set<string>()

function runPrefetch(kind: 'podcast' | 'video', id: string) {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection
  if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || '')) return
  const key = kind === 'podcast' ? CacheKeys.SUMMARY(id) : CacheKeys.VIDEO_NOTE(id)
  const owner = getAccountId()
  const generation = getAuthGeneration()
  const revision = getReadRevision()
  const requestKey = `${generation}:${revision}:${key}`
  if (getCache(key) || pending.has(requestKey) || pending.size >= 2) return
  pending.add(requestKey)
  preloadPage(kind === 'podcast' ? `/viewer/${id}` : `/videos/${id}`)
  const request = kind === 'podcast' ? fetchSummary(id) : fetchVideoTask(id)
  void request.then(data => {
    if (owner === getAccountId() && generation === getAuthGeneration() && revision === getReadRevision()) {
      if (kind === 'podcast' || ('status' in data && data.status === 'success')) setCache(key, data, owner)
    }
  }).catch(() => {}).finally(() => pending.delete(requestKey))
}

let timer: ReturnType<typeof setTimeout> | undefined
export function cancelPrefetch() { clearTimeout(timer) }
function schedule(kind: 'podcast'|'video', id:string) {
  cancelPrefetch()
  timer = setTimeout(() => { if (document.visibilityState !== 'hidden') runPrefetch(kind, id) }, 200)
}
export function prefetchSummary(id: string) { schedule('podcast', id) }
export function prefetchVideoNote(id: string) { schedule('video', id) }
