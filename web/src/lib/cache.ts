import { useEffect } from 'react'
import { getAccountId } from './preferences'

const CACHE_PREFIX = 'xyz_cache_'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000
const MAX_BYTES = 16 * 1024 * 1024
const MAX_ENTRIES = 80
interface Entry {key:string;data:unknown;timestamp:number;accessed:number;bytes:number}
const memory = new Map<string,Entry>()
let revision=0
let database:Promise<IDBDatabase|null>|undefined
let queue=Promise.resolve()
let hydratedOwner=''
let hydrating:Promise<void>|undefined
const scoped=(key:string)=>`${CACHE_PREFIX}${getAccountId()}:${key}`
const small=(key:string)=>key==='settings'||key==='stats'
function size(value:unknown):number { if(typeof value==='string')return value.length*2;if(Array.isArray(value))return value.reduce((n,v)=>n+size(v),0);if(value&&typeof value==='object')return Object.entries(value).reduce((n,[k,v])=>n+k.length*2+size(v),0);return 8 }
function openDB() {
  if(!database) database=new Promise(resolve=>{
    if(typeof indexedDB==='undefined'){resolve(null);return}
    const request=indexedDB.open('xyz-private-cache',1)
    request.onupgradeneeded=()=>request.result.createObjectStore('entries',{keyPath:'key'})
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>resolve(null);request.onblocked=()=>resolve(null)
  })
  return database
}
function enqueue(action:(db:IDBDatabase)=>void) { queue=queue.then(async()=>{const db=await openDB();if(db)action(db)}).catch(()=>{}) }
function trim() {
  let bytes=Array.from(memory.values()).reduce((n,e)=>n+e.bytes,0)
  for(const entry of [...memory.values()].sort((a,b)=>a.accessed-b.accessed)) {
    if(memory.size<=MAX_ENTRIES&&bytes<=MAX_BYTES)break
    memory.delete(entry.key);bytes-=entry.bytes
    enqueue(db=>db.transaction('entries','readwrite').objectStore('entries').delete(entry.key))
  }
}
export async function hydrateCache() {
  const owner=getAccountId()
  if(hydratedOwner===owner)return hydrating
  hydratedOwner=owner
  const epoch=revision
  hydrating=(async()=>{
    // Discard legacy bulky localStorage entries without parsing large JSON on startup.
    for(const key of Object.keys(localStorage)) if(key.startsWith(CACHE_PREFIX)&&!key.endsWith(':settings')&&!key.endsWith(':stats'))localStorage.removeItem(key)
    const db=await openDB();if(!db)return
    await new Promise<void>(resolve=>{
      const tx=db.transaction('entries','readwrite'), request=tx.objectStore('entries').openCursor()
      request.onsuccess=()=>{const row=request.result;if(!row)return;const entry=row.value as Entry
        if(epoch!==revision||owner!==getAccountId()){row.continue();return}
        if(Date.now()-entry.timestamp>CACHE_TTL_MS || !entry.key.startsWith(`${CACHE_PREFIX}${owner}:`))row.delete()
        else if(epoch===revision&&owner===getAccountId()&&!memory.has(entry.key))memory.set(entry.key,entry)
        row.continue()
      }
      tx.oncomplete=()=>{trim();resolve()};tx.onerror=()=>resolve();tx.onabort=()=>resolve()
    })
  })().catch(()=>{})
  return hydrating
}
export function useWarmCache<T>(key:string, apply:(value:T)=>void) {
  useEffect(()=>{let active=true;const owner=getAccountId();void hydrateCache().then(()=>{if(active&&owner===getAccountId()){const value=getCache<T>(key);if(value!==null)apply(value)}});return()=>{active=false}},[key])
}
export function getCache<T>(key:string):T|null {
  const name=scoped(key),entry=memory.get(name)
  if(entry&&Date.now()-entry.timestamp<CACHE_TTL_MS){const touch=Date.now()-entry.accessed>30000;entry.accessed=Date.now();if(touch){const epoch=revision;enqueue(db=>{if(epoch===revision&&memory.get(name)===entry)db.transaction('entries','readwrite').objectStore('entries').put(entry)})}return entry.data as T}
  if(entry)removeCache(key)
  if(small(key))try {const data=JSON.parse(localStorage.getItem(name)||'null');if(data&&Date.now()-data.timestamp<CACHE_TTL_MS)return data.data as T}catch{}
  return null
}
export function setCache<T>(key:string,data:T,owner=getAccountId()) {
  if(owner!==getAccountId())return
  const name=scoped(key), bytes=size(data)
  if(bytes>2*1024*1024)return
  const entry:Entry={key:name,data,timestamp:Date.now(),accessed:Date.now(),bytes}
  memory.set(name,entry);trim()
  if(small(key)&&bytes<32768)try{localStorage.setItem(name,JSON.stringify(entry))}catch{}
  const epoch=revision
  enqueue(db=>{if(epoch===revision&&owner===getAccountId()&&memory.has(name)){const tx=db.transaction('entries','readwrite');tx.objectStore('entries').put(entry)}})
}
export function removeCache(key:string) {revision++;const name=scoped(key);memory.delete(name);try{localStorage.removeItem(name)}catch{};enqueue(db=>db.transaction('entries','readwrite').objectStore('entries').delete(name))}
export function clearCache() {revision++;memory.clear();hydratedOwner='';for(const key of Object.keys(localStorage))if(key.startsWith(CACHE_PREFIX))localStorage.removeItem(key);enqueue(db=>db.transaction('entries','readwrite').objectStore('entries').clear())}

/**
 * Cache keys for different data types
 */
export const CacheKeys = {
  STATS: 'stats',
  SETTINGS: 'settings',
  PODCASTS: 'podcasts',
  PODCAST: (pid: string) => `podcast_${pid}`,
  SUMMARIES: 'summaries',
  RECENT_SUMMARIES: 'recent_summaries',
  RECENT_VIDEOS: 'recent_videos',
  VIDEO_CHANNELS: 'video_channels',
  CHANNEL_VIDEOS: (platform: string, channel: string) => `channel_videos_${JSON.stringify([platform, channel])}`,
  SUMMARY: (eid: string) => `summary_${eid}`,
  VIDEO_NOTE: (id: string) => `video_note_${id}`,
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
  // Begin networking immediately; disk hydration must not add a waterfall.
  const pending = fetchFn()
  void pending.catch(() => {})
  await hydrateCache()
  if (owner !== getAccountId()) throw new DOMException('Account changed', 'AbortError')
  const cached = getCache<T>(key)
  if (cached && options.onCached) {
    options.onCached(cached)
  }

  // Fetch fresh data
  try {
    const fresh = await pending
    if (owner !== getAccountId()) throw new DOMException('Account changed', 'AbortError')
    setCache(key, fresh, owner)
    if (options.onFresh) {
      options.onFresh(fresh)
    }
    return fresh
  } catch (error) {
    if (owner !== getAccountId()) throw new DOMException('Account changed', 'AbortError')
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

/** Invalidate only related account data; keep unrelated pages warm. */
export function invalidateForMutation(url: string): void {
  const path = new URL(url, location.origin).pathname.replace(/^\/api\//, '')
  let prefixes: string[]
  if (/^settings/.test(path)) prefixes = ['settings']
  else if (/^(cookies|notion)/.test(path)) prefixes = []
  else if (/^video-notes/.test(path)) prefixes = ['video_', 'channel_', 'recent_videos', 'library_page:', 'stats']
  else if (/^(podcasts|episodes|summaries|process|jobs|check-podcasts|truncated)/.test(path)) prefixes = ['podcast', 'episodes_', 'summary_', 'summaries', 'recent_summaries', 'transcript_', 'library_page:', 'stats']
  else prefixes = []
  const accountPrefix = `${CACHE_PREFIX}${getAccountId()}:`
  revision++
  for (const key of Object.keys(localStorage)) if (key.startsWith(accountPrefix) && prefixes.some(prefix => key.slice(accountPrefix.length).startsWith(prefix))) localStorage.removeItem(key)
  for (const key of memory.keys()) if (key.startsWith(accountPrefix) && prefixes.some(prefix => key.slice(accountPrefix.length).startsWith(prefix))) memory.delete(key)
  enqueue(db => { const tx=db.transaction('entries','readwrite'); const cursor=tx.objectStore('entries').openCursor();cursor.onsuccess=()=>{const row=cursor.result;if(!row)return;const key=String(row.key);if(key.startsWith(accountPrefix)&&prefixes.some(prefix=>key.slice(accountPrefix.length).startsWith(prefix)))row.delete();row.continue()} })
}
