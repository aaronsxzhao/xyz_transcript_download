import { useEffect, useMemo, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { accessTokenNeedsRefresh, getAccessToken } from './auth'
import { getCache } from './cache'

let currentPath = window.location.pathname + window.location.search
let visitId = (window as Window & {__xyzVisit?:string}).__xyzVisit || crypto.randomUUID()
let started = 0 // Include document/network startup on a hard navigation.

export function markPageNavigation(path: string) {
  if (path !== currentPath) { currentPath = path; started = performance.now(); visitId = crypto.randomUUID() }
}

type Page = 'library' | 'dashboard' | 'podcasts' | 'videos' | 'channel' | 'episodes' | 'viewer' | 'video_note' | 'settings'

function isPageRead(page: Page, path: string) {
  if (page === 'library') return path === '/api/library'
  if (page === 'settings') return path === '/api/settings'
  if (page === 'viewer') return /^\/api\/(summaries|transcripts)\//.test(path)
  if (page === 'video_note') return /^\/api\/video-notes\/tasks\/[^/]+$/.test(path)
  if (page === 'episodes') return /^\/api\/podcasts\//.test(path)
  if (page === 'podcasts') return path === '/api/podcasts'
  if (page === 'channel') return path === '/api/video-notes/tasks/by-channel'
  if (page === 'videos') return path === '/api/video-notes/channels'
  return path === '/api/stats' || path === '/api/summaries/recent' || path === '/api/video-notes/recent'
}

export function usePageTiming(page: Page, ready: boolean, cacheKey: string, failed = false) {
  const { pathname, search } = useLocation()
  const route = pathname + search
  const reported = useRef('')
  const usedCache = useMemo(() => getCache(cacheKey) !== null, [route, cacheKey])
  useEffect(() => {
    const report = (outcome: 'ready' | 'slow' | 'error') => {
      const key = visitId + ':' + outcome
      if (reported.current === key) return
      const token = getAccessToken()
      if (!token || accessTokenNeedsRefresh(token)) return
      reported.current = key
      const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
      const requests = (performance.getEntriesByType('resource') as PerformanceResourceTiming[])
        .filter(entry => entry.startTime >= started && isPageRead(page, new URL(entry.name).pathname))
      const longest = requests.sort((a, b) => b.duration - a.duration)[0]
      const bounded = (value: number) => Math.max(0, Math.min(300000, Math.round(value)))
      // Fixed labels and durations only; no private URLs or page contents.
      void fetch('/api/performance', { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ page, outcome, visit_id:visitId, navigation:started===0?'document':'navigation', stage: outcome === 'ready' && ['viewer','video_note'].includes(page) ? 'content' : 'application', program_embedded: !!document.querySelector('[data-document-program]'), elapsed_ms: bounded(performance.now() - started),
          first_paint_ms: bounded(started === 0 ? performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0 : 0),
          document_ms: bounded(started === 0 ? navigation?.responseEnd || 0 : 0),
          api_ms: bounded(longest?.duration || 0),
          server_ms: bounded(longest?.serverTiming?.find(timing => timing.name === 'app')?.duration || 0),
          cached: usedCache || getCache(cacheKey) !== null && requests.length === 0 }),
      }).catch(() => {})
    }
    if (failed) report('error')
    else if (ready) report('ready')
    else {
      // A hanging or failed page must remain visible to diagnostics as well.
      const timeout = window.setTimeout(() => report('slow'), 10000)
      return () => window.clearTimeout(timeout)
    }
  }, [route, page, ready, failed])
}

const imageReports = new Set<string>()
export function recordReaderImage(_milliseconds: number, src: string) {
  const key = visitId
  const token = getAccessToken()
  if (!token || imageReports.has(key)) return
  const entries = performance.getEntriesByName(new URL(src,location.origin).href)
  const resource = entries[entries.length-1] as PerformanceResourceTiming|undefined
  const cached = !!resource && resource.transferSize===0 && resource.decodedBodySize>0
  imageReports.add(key)
  if (imageReports.size > 100) imageReports.delete(imageReports.values().next().value!)
  void fetch('/api/performance', {method:'POST',keepalive:true,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({page:location.pathname.startsWith('/viewer/')?'viewer':'video_note',stage:'image',visit_id:visitId,navigation:started===0?'document':'navigation',elapsed_ms:Math.max(0,Math.min(300000,Math.round(performance.now()-started))),document_ms:0,api_ms:0,cached})}).catch(()=>{})
}
