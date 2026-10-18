import { getAccountId } from './preferences'
/**
 * Browser localStorage cache for offline access and fast loading
 */

const CACHE_PREFIX = 'xyz_cache_'
const CACHE_VERSION = 'v5'  // Bumped to invalidate old cached data
const CACHE_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours

interface CacheEntry<T> {
  data: T
  timestamp: number
  version: string
}

/**
 * Get cached data
 */
export function getCache<T>(key: string): T | null {
  try {
    const stored = localStorage.getItem(`${CACHE_PREFIX}${getAccountId()}:${key}`)
    if (!stored) return null

    const entry: CacheEntry<T> = JSON.parse(stored)

    // Check version
    if (entry.version !== CACHE_VERSION) {
      localStorage.removeItem(`${CACHE_PREFIX}${getAccountId()}:${key}`)
      return null
    }

    // Check TTL
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(`${CACHE_PREFIX}${getAccountId()}:${key}`)
      return null
    }

    return entry.data
  } catch {
    return null
  }
}

/**
 * Set cached data
 */
export function setCache<T>(key: string, data: T, owner = getAccountId()): void {
  if (owner !== getAccountId()) return
  try {
    const entry: CacheEntry<T> = {
      data,
      timestamp: Date.now(),
      version: CACHE_VERSION,
    }
    localStorage.setItem(`${CACHE_PREFIX}${getAccountId()}:${key}`, JSON.stringify(entry))
  } catch (e) {
    // localStorage might be full or disabled
    console.warn('Failed to cache data:', e)
  }
}

/**
 * Remove cached data
 */
export function removeCache(key: string): void {
  localStorage.removeItem(`${CACHE_PREFIX}${getAccountId()}:${key}`)
}

/**
 * Clear all cached data
 */
export function clearCache(): void {
  const keys = Object.keys(localStorage)
  for (const key of keys) {
    if (key.startsWith(CACHE_PREFIX)) {
      localStorage.removeItem(key)
    }
  }
}

/**
 * Cache keys for different data types
 */
export const CacheKeys = {
  STATS: 'stats',
  PODCASTS: 'podcasts',
  SUMMARIES: 'summaries',
  RECENT_SUMMARIES: 'recent_summaries',
  RECENT_VIDEOS: 'recent_videos',
  SUMMARY: (eid: string) => `summary_${eid}`,
  TRANSCRIPT: (eid: string) => `transcript_${eid}`,
  EPISODES: (pid: string) => `episodes_${pid}`,
}

/**
 * Fetch with cache - returns cached data immediately, then fetches fresh data
 */
export async function fetchWithCache<T>(
  key: string,
  fetchFn: () => Promise<T>,
  options: {
    onCached?: (data: T) => void
    onFresh?: (data: T) => void
    onError?: (error: Error) => void
  } = {}
): Promise<T> {
  const owner = getAccountId()
  // Return cached data immediately if available
  const cached = getCache<T>(key)
  if (cached && options.onCached) {
    options.onCached(cached)
  }

  // Fetch fresh data
  try {
    const fresh = await fetchFn()
    if (owner !== getAccountId()) throw new DOMException('Account changed', 'AbortError')
    setCache(key, fresh, owner)
    if (options.onFresh) {
      options.onFresh(fresh)
    }
    return fresh
  } catch (error) {
    if (options.onError) {
      options.onError(error as Error)
    }
    // If fetch fails but we have cache, return cache
    if (cached) {
      return cached
    }
    throw error
  }
}
