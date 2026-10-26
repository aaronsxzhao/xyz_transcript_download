import { useEffect } from "react";
import { getAccountId } from "./preferences";

const CACHE_PREFIX = "xyz_cache_";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const MAX_BYTES = 16 * 1024 * 1024;
const MAX_ENTRIES = 80;
interface Entry {
  key: string;
  data: unknown;
  timestamp: number;
  accessed: number;
  bytes: number;
}
const memory = new Map<string, Entry>();
const listeners = new Map<string, Set<() => void>>();
let revision = 0;
let database: Promise<IDBDatabase | null> | undefined;
let queue = Promise.resolve();
const hydration = new Map<string, Promise<void>>();
let maintenanceScheduled = false;
const scoped = (key: string) => `${CACHE_PREFIX}${getAccountId()}:${key}`;
const ttl = (key: string) =>
  key.endsWith(":reading_history") ? 90 * CACHE_TTL_MS : CACHE_TTL_MS;
const small = (key: string) => key === "settings" || key === "stats";
function size(value: unknown): number {
  if (typeof value === "string") return value.length * 2;
  if (Array.isArray(value)) return value.reduce((n, v) => n + size(v), 0);
  if (value && typeof value === "object")
    return Object.entries(value).reduce(
      (n, [k, v]) => n + k.length * 2 + size(v),
      0,
    );
  return 8;
}
// Storage is optional: a stalled browser database must never block networking or tools.
function openDB() {
  if (!database)
    database = new Promise((resolve) => {
      if (typeof indexedDB === "undefined") {
        resolve(null);
        return;
      }
      const timer = setTimeout(() => {
        database = undefined;
        resolve(null);
      }, 1000);
      try {
        const request = indexedDB.open("xyz-private-cache", 1);
        request.onupgradeneeded = () =>
          request.result.createObjectStore("entries", { keyPath: "key" });
        request.onsuccess = () => {
          clearTimeout(timer);
          const db = request.result;
          db.onversionchange = () => {
            db.close();
            database = undefined;
          };
          database = Promise.resolve(db);
          resolve(db);
        };
        request.onerror = request.onblocked = () => {
          clearTimeout(timer);
          database = undefined;
          resolve(null);
        };
      } catch {
        clearTimeout(timer);
        resolve(null);
      }
    });
  return database;
}
function enqueue(action: (db: IDBDatabase) => void) {
  queue = queue
    .then(async () => {
      const db = await openDB();
      if (db) action(db);
    })
    .catch(() => {});
}
function trim() {
  let bytes = Array.from(memory.values()).reduce((n, e) => n + e.bytes, 0);
  for (const entry of [...memory.values()].sort(
    (a, b) => a.accessed - b.accessed,
  )) {
    if (memory.size <= MAX_ENTRIES && bytes <= MAX_BYTES) break;
    if (entry.key.endsWith(":reading_history")) continue;
    memory.delete(entry.key);
    bytes -= entry.bytes;
    enqueue((db) =>
      db
        .transaction("entries", "readwrite")
        .objectStore("entries")
        .delete(entry.key),
    );
  }
}
// Read only the requested record on the critical path. Whole-cache maintenance
// runs when the browser is idle and never hydrates unrelated note bodies.
function scheduleMaintenance() {
  if (maintenanceScheduled) return;
  maintenanceScheduled = true;
  const run = () => {
    maintenanceScheduled = false;
    const epoch = revision;
    enqueue((db) => {
      if (epoch !== revision) return;
      const tx = db.transaction("entries", "readwrite"),
        store = tx.objectStore("entries");
      const entries: Omit<Entry, "data">[] = [];
      const cursor = store.openCursor();
      cursor.onsuccess = () => {
        const row = cursor.result;
        if (epoch !== revision) {
          tx.abort();
          return;
        }
        if (row) {
          const { key, timestamp, accessed, bytes } = row.value as Entry;
          if (Date.now() - timestamp >= ttl(key)) row.delete();
          else entries.push({ key, timestamp, accessed, bytes });
          row.continue();
        } else {
          let bytes = entries.reduce((n, e) => n + e.bytes, 0),
            count = entries.length;
          for (const entry of entries.sort((a, b) => a.accessed - b.accessed)) {
            if (count <= MAX_ENTRIES && bytes <= MAX_BYTES) break;
            if (entry.key.endsWith(":reading_history")) continue;
            store.delete(entry.key);
            count--;
            bytes -= entry.bytes;
          }
        }
      };
    });
    for (const key of Object.keys(localStorage))
      if (
        key.startsWith(CACHE_PREFIX) &&
        !key.endsWith(":settings") &&
        !key.endsWith(":stats")
      )
        localStorage.removeItem(key);
  };
  setTimeout(() => {
    if ("requestIdleCallback" in window)
      window.requestIdleCallback(run, { timeout: 10000 });
    else setTimeout(run, 1000);
  }, 10000);
}
export async function hydrateCache(key?: string): Promise<void> {
  scheduleMaintenance();
  if (!key) return;
  const name = scoped(key),
    owner = getAccountId(),
    epoch = revision;
  if (memory.has(name)) return;
  const existing = hydration.get(name);
  if (existing) return existing;
  const pending = (async () => {
    const db = await openDB();
    if (!db) return;
    await new Promise<void>((resolve) => {
      const request = db
        .transaction("entries", "readonly")
        .objectStore("entries")
        .get(name);
      request.onsuccess = () => {
        const entry = request.result as Entry | undefined;
        if (
          entry &&
          Date.now() - entry.timestamp < ttl(entry.key) &&
          epoch === revision &&
          owner === getAccountId() &&
          !memory.has(name)
        ) {
          memory.set(name, entry);
          trim();
        }
        resolve();
      };
      request.onerror = () => resolve();
    });
  })().catch(() => {});
  hydration.set(name, pending);
  let timer: ReturnType<typeof setTimeout>;
  try {
    await Promise.race([
      pending,
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, 1000);
      }),
    ]);
  } finally {
    clearTimeout(timer!);
    if (hydration.get(name) === pending) hydration.delete(name);
  }
}
export function useWarmCache<T>(key: string, apply: (value: T) => void) {
  useEffect(() => {
    let active = true;
    const owner = getAccountId(),
      name = scoped(key);
    const update = () => {
      if (active && owner === getAccountId()) {
        const value = getCache<T>(key);
        if (value !== null) apply(value);
      }
    };
    const subscribers = listeners.get(name) || new Set<() => void>();
    subscribers.add(update);
    listeners.set(name, subscribers);
    void hydrateCache(key).then(update);
    return () => {
      active = false;
      subscribers.delete(update);
      if (!subscribers.size) listeners.delete(name);
    };
  }, [key]);
}
export function getCache<T>(key: string): T | null {
  const name = scoped(key),
    entry = memory.get(name);
  if (entry && Date.now() - entry.timestamp < ttl(entry.key)) {
    const touch = Date.now() - entry.accessed > 30000;
    entry.accessed = Date.now();
    if (touch) {
      const epoch = revision;
      enqueue((db) => {
        if (epoch === revision && memory.get(name) === entry)
          db.transaction("entries", "readwrite")
            .objectStore("entries")
            .put(entry);
      });
    }
    return entry.data as T;
  }
  if (entry) removeCache(key);
  if (small(key))
    try {
      const data = JSON.parse(localStorage.getItem(name) || "null");
      if (data && Date.now() - data.timestamp < CACHE_TTL_MS)
        return data.data as T;
    } catch {}
  return null;
}
export function getCacheAge(key: string): number | null {
  const entry = memory.get(scoped(key));
  return entry ? Date.now() - entry.timestamp : null;
}
export function setCache<T>(key: string, data: T, owner = getAccountId()) {
  if (owner !== getAccountId()) return;
  const name = scoped(key),
    bytes = size(data);
  if (bytes > 2 * 1024 * 1024) return;
  const entry: Entry = {
    key: name,
    data,
    timestamp: Date.now(),
    accessed: Date.now(),
    bytes,
  };
  memory.set(name, entry);
  trim();
  scheduleMaintenance();
  queueMicrotask(() => {
    if (owner === getAccountId() && memory.get(name) === entry)
      listeners.get(name)?.forEach((update) => update());
  });
  if (small(key) && bytes < 32768)
    try {
      localStorage.setItem(name, JSON.stringify(entry));
    } catch {}
  const epoch = revision;
  enqueue((db) => {
    if (epoch === revision && owner === getAccountId() && memory.has(name)) {
      const tx = db.transaction("entries", "readwrite");
      tx.objectStore("entries").put(entry);
    }
  });
}
export function removeCache(key: string) {
  revision++;
  const name = scoped(key);
  memory.delete(name);
  try {
    localStorage.removeItem(name);
  } catch {}
  enqueue((db) =>
    db.transaction("entries", "readwrite").objectStore("entries").delete(name),
  );
}
export function clearCache() {
  revision++;
  memory.clear();
  hydration.clear();
  for (const key of Object.keys(localStorage))
    if (key.startsWith(CACHE_PREFIX)) localStorage.removeItem(key);
  enqueue((db) =>
    db.transaction("entries", "readwrite").objectStore("entries").clear(),
  );
}

/**
 * Cache keys for different data types
 */
export const CacheKeys = {
  STATS: "stats",
  SETTINGS: "settings",
  PODCASTS: "podcasts",
  PODCAST: (pid: string) => `podcast_${pid}`,
  SUMMARIES: "summaries",
  RECENT_SUMMARIES: "recent_summaries:v2",
  RECENT_VIDEOS: "recent_videos",
  VIDEO_CHANNELS: "video_channels",
  CHANNEL_VIDEOS: (platform: string, channel: string) =>
    `channel_videos_${JSON.stringify([platform, channel])}`,
  SUMMARY: (eid: string) => `summary_${eid}`,
  VIDEO_NOTE: (id: string) => `video_note_${id}`,
  TRANSCRIPT: (eid: string) => `transcript_${eid}`,
  EPISODES: (pid: string) => `episodes_${pid}`,
};

/**
 * Fetch with cache - returns cached data immediately, then fetches fresh data
 */
export async function fetchWithCache<T>(
  key: string,
  fetchFn: () => Promise<T>,
  options: {
    onCached?: (data: T) => void;
    onFresh?: (data: T) => void;
    onError?: (error: Error) => void;
  } = {},
): Promise<T> {
  const owner = getAccountId();
  // Begin networking immediately; disk hydration must not add a waterfall.
  const pending = fetchFn();
  void pending.catch(() => {});
  await hydrateCache(key);
  if (owner !== getAccountId())
    throw new DOMException("Account changed", "AbortError");
  const cached = getCache<T>(key);
  if (cached && options.onCached) {
    options.onCached(cached);
  }

  // Fetch fresh data
  try {
    const fresh = await pending;
    if (owner !== getAccountId())
      throw new DOMException("Account changed", "AbortError");
    setCache(key, fresh, owner);
    if (options.onFresh) {
      options.onFresh(fresh);
    }
    return fresh;
  } catch (error) {
    if (owner !== getAccountId())
      throw new DOMException("Account changed", "AbortError");
    if (options.onError) {
      options.onError(error as Error);
    }
    // If fetch fails but we have cache, return cache
    if (cached) {
      return cached;
    }
    throw error;
  }
}

/** Invalidate only related account data; keep unrelated pages warm. */
export function invalidateForMutation(url: string): void {
  const path = new URL(url, location.origin).pathname.replace(/^\/api\//, "");
  let prefixes: string[];
  if (path === "settings") prefixes = ["settings"];
  else if (/^(cookies|notion)/.test(path)) prefixes = [];
  else if (/^video-notes/.test(path))
    prefixes = [
      "video_",
      "channel_",
      "recent_videos",
      "library_page:",
      "stats",
    ];
  else if (
    /^(podcasts|episodes|summaries|process|jobs|check-podcasts|truncated)/.test(
      path,
    )
  )
    prefixes = [
      "podcast",
      "episodes_",
      "summary_",
      "summaries",
      "recent_summaries",
      "transcript_",
      "library_page:",
      "stats",
    ];
  else prefixes = [];
  const accountPrefix = `${CACHE_PREFIX}${getAccountId()}:`;
  revision++;
  for (const key of Object.keys(localStorage))
    if (
      key.startsWith(accountPrefix) &&
      prefixes.some((prefix) =>
        key.slice(accountPrefix.length).startsWith(prefix),
      )
    )
      localStorage.removeItem(key);
  for (const key of memory.keys())
    if (
      key.startsWith(accountPrefix) &&
      prefixes.some((prefix) =>
        key.slice(accountPrefix.length).startsWith(prefix),
      )
    )
      memory.delete(key);
  enqueue((db) => {
    const tx = db.transaction("entries", "readwrite");
    const cursor = tx.objectStore("entries").openCursor();
    cursor.onsuccess = () => {
      const row = cursor.result;
      if (!row) return;
      const key = String(row.key);
      if (
        key.startsWith(accountPrefix) &&
        prefixes.some((prefix) =>
          key.slice(accountPrefix.length).startsWith(prefix),
        )
      )
        row.delete();
      row.continue();
    };
  });
}
