import { useEffect, useRef } from 'react'

const retryEvent = 'xyz:retry-connection'
export const retryConnection = () => window.dispatchEvent(new Event(retryEvent))
export const isConnectionError = (message: string) => /fetch|network|connection|timed? out|timeout|offline|unavailable|\b50[234]\b/i.test(message)

/** Retry failed reads on recovery, not every focus while the page is healthy. */
export function useConnectionRecovery(retry: () => void, enabled: boolean) {
  const latest = useRef(retry)
  latest.current = retry
  useEffect(() => {
    if (!enabled) return
    let last = -Infinity
    const recover = () => {
      if (document.visibilityState === 'hidden' || Date.now() - last < 1000) return
      last = Date.now()
      latest.current()
    }
    for (const event of ['online', 'focus', retryEvent]) window.addEventListener(event, recover)
    document.addEventListener('visibilitychange', recover)
    return () => {
      for (const event of ['online', 'focus', retryEvent]) window.removeEventListener(event, recover)
      document.removeEventListener('visibilitychange', recover)
    }
  }, [enabled])
}
