import { useEffect, useMemo, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { accessTokenNeedsRefresh, getAccessToken } from './auth'
import { getCache } from './cache'

let currentPath = window.location.pathname
let started = 0 // Include document/network startup on a hard navigation.

export function markPageNavigation(path: string) {
  if (path !== currentPath) { currentPath = path; started = performance.now() }
}

export function usePageTiming(page: 'dashboard' | 'podcasts' | 'videos' | 'episodes' | 'viewer', ready: boolean, cacheKey: string) {
  const { pathname } = useLocation()
  const reported = useRef('')
  const usedCache = useMemo(() => getCache(cacheKey) !== null, [pathname, cacheKey])
  useEffect(() => {
    if (!ready || reported.current === pathname) return
    reported.current = pathname
    const token = getAccessToken()
    if (!token || accessTokenNeedsRefresh(token)) return
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const requests = (performance.getEntriesByType('resource') as PerformanceResourceTiming[])
      .filter(entry => entry.startTime >= started && new URL(entry.name).pathname.startsWith('/api/'))
    const bounded = (value: number) => Math.max(0, Math.min(300000, Math.round(value)))
    // This reports fixed page labels and durations only, outside the loading
    // path. Use fetch directly so telemetry does not invalidate cached pages.
    void fetch('/api/performance', { method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ page, elapsed_ms: bounded(performance.now() - started),
        document_ms: bounded(started === 0 ? navigation?.responseEnd || 0 : 0),
        api_ms: bounded(Math.max(0, ...requests.map(entry => entry.duration))), cached: usedCache }),
    }).catch(() => {})
  }, [pathname, page, ready])
}
