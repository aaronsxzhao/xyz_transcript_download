/**
 * Tracks how many times a user has "seen" an item on screen.
 * Used for:
 *  - "Newly Added" badge: shown until viewCount >= 2
 *  - Auto-dismiss completed tasks: dismissed once viewCount >= 1
 *
 * Data is stored in localStorage and capped to prevent unbounded growth.
 */

const STORAGE_KEY = 'xyz_seen_items'
const MAX_ENTRIES = 500

interface SeenMap {
  [id: string]: number
}

function load(): SeenMap {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function save(map: SeenMap) {
  const keys = Object.keys(map)
  if (keys.length > MAX_ENTRIES) {
    const sorted = keys.sort((a, b) => map[a] - map[b])
    for (const k of sorted.slice(0, keys.length - MAX_ENTRIES)) {
      delete map[k]
    }
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
}

/** Increment view count for a batch of IDs. Call once per page load. */
export function markSeen(ids: string[]) {
  if (!ids.length) return
  const map = load()
  for (const id of ids) {
    map[id] = (map[id] || 0) + 1
  }
  save(map)
}

/** How many times the user has seen this item. */
export function getViewCount(id: string): number {
  return load()[id] || 0
}

/** True if item should show "Newly Added" badge (seen < 2 times). */
export function isNewItem(id: string): boolean {
  return getViewCount(id) < 2
}

/** True if a completed task should be auto-dismissed (seen >= 1 time). */
export function shouldDismissCompleted(id: string): boolean {
  return getViewCount(id) >= 1
}
