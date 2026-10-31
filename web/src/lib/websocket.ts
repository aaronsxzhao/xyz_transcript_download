/** Account-bound real-time updates with polling when the socket is unavailable. */
import { useStore } from './store'
import { authFetch, fetchProgress } from './api'
import { getAccessToken, refreshToken } from './auth'
import {requestWithDeadline} from './requestDeadline'

let running = false
let epoch = 0
let ws: WebSocket | null = null
let pollTimer: number | undefined
let reconnectTimer: number | undefined
let staleTimer: number | undefined
let lastUpdate = 0
let connectingSince = 0
let refreshRevision = 0
type Stream = 'podcast' | 'video'
const inFlight:Partial<Record<Stream,AbortController>> = {}
const lastSnapshot:Record<Stream,number> = {podcast:0,video:0}
const active = (status: string) => !['completed', 'success', 'failed', 'cancelled', 'discovered'].includes(status)

/** Streams reconcile independently. Socket activity is not proof of fresh task data. */
function pollJobs(owner:number) {
  if (!running || owner!==epoch) return
  const state=useStore.getState()
  const busy={podcast:state.jobs.some(job=>active(job.status)),video:state.videoTasks.some(task=>active(task.status))}
  const healthySocket=state.wsConnected && ws?.readyState===WebSocket.OPEN && Date.now()-lastUpdate<45000
  if(document.visibilityState!=='hidden') for(const stream of ['podcast','video'] as const) {
    if(inFlight[stream] || (healthySocket && !busy[stream] && Date.now()-lastSnapshot[stream]<30000)) continue
    const controller=new AbortController(),revision=refreshRevision
    inFlight[stream]=controller
    const current=()=>running && owner===epoch && revision===refreshRevision && !controller.signal.aborted
    const request=stream==='podcast'
      ? requestWithDeadline(async signal=>{
          const response=await authFetch('/api/jobs',{signal,cache:'no-store'})
          if(!response.ok)throw new Error('Cannot refresh podcast progress')
          const data=await response.json()
          if(!Array.isArray(data.jobs))throw new Error('Invalid podcast progress response')
          return data.jobs
        },{signal:controller.signal}).then(jobs=>{if(current())useStore.getState().mergeJobs(jobs)})
      : fetchProgress(state.videoTasks.filter(task=>active(task.status)).map(task=>task.id),controller.signal).then(data=>{
          if(current())useStore.getState().mergeVideoTasks(data.tasks)
        })
    void request.then(()=>{if(current())lastSnapshot[stream]=Date.now()})
      .catch(error=>{if(current())console.debug('Progress refresh failed:',error)})
      .finally(()=>{if(inFlight[stream]===controller)delete inFlight[stream]})
  }
  // A response can discover active work after this tick was scheduled.
  // Keep the tick short; per-stream freshness still bounds idle network reads.
  pollTimer=window.setTimeout(()=>pollJobs(owner),busy.podcast || busy.video ? 2000 : 5000)
}

function refreshProgress() {
  if(!running || document.visibilityState==='hidden')return
  refreshRevision++
  for(const stream of ['podcast','video'] as const){inFlight[stream]?.abort();delete inFlight[stream];lastSnapshot[stream]=0}
  window.clearTimeout(pollTimer)
  pollTimer=window.setTimeout(()=>pollJobs(epoch),0)
}

function openSocket(owner: number) {
  if (!running || owner !== epoch) return
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/ws/progress`)
  ws = socket
  connectingSince = Date.now()
  const current = () => running && owner === epoch && ws === socket
  socket.onopen = () => {
    if (current()) socket.send(JSON.stringify({ type: 'auth', token: getAccessToken() || undefined }))
  }
  socket.onmessage = event => {
    if (!current()) return
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'init') {
        lastUpdate = Date.now()
        useStore.getState().setWsConnected(true)
        useStore.getState().mergeJobs(data.jobs || [])
        useStore.getState().mergeVideoTasks(data.video_tasks || [])
      } else if (data.type === 'job_update' && data.job) {
        lastUpdate = Date.now()
        useStore.getState().updateJob(data.job)
      } else if (data.type === 'video_job_update' && data.task) {
        lastUpdate = Date.now()
        useStore.getState().updateVideoTask(data.task)
      } else if (data.type === 'heartbeat') {
        lastUpdate = Date.now()
        socket.send(JSON.stringify({ type: 'ping' }))
      }
    } catch (error) { console.debug('Invalid progress message:', error) }
  }
  socket.onclose = event => {
    if (!current()) return
    useStore.getState().setWsConnected(false)
    lastUpdate = 0
    reconnectTimer = window.setTimeout(async () => {
      try { if (event.code === 4401) await refreshToken() } catch { /* polling retries later */ }
      if (current()) openSocket(owner)
    }, 3000)
  }
  socket.onerror = () => { if (current()) useStore.getState().setWsConnected(false) }
}

export function connectWebSocket() {
  if (running) return
  running = true
  const owner = ++epoch
  lastSnapshot.podcast=lastSnapshot.video=Date.now()
  window.addEventListener('xyz:processing-changed',refreshProgress)
  window.addEventListener('focus',refreshProgress)
  window.addEventListener('online',refreshProgress)
  window.addEventListener('pageshow',refreshProgress)
  document.addEventListener('visibilitychange',refreshProgress)
  pollTimer = window.setTimeout(() => { void pollJobs(owner) }, 5000)
  openSocket(owner)
  staleTimer = window.setInterval(() => {
    const state = useStore.getState()
    const stalledHandshake = !state.wsConnected && Date.now() - connectingSince > 30000
    if (ws && ws.readyState < 2 && (stalledHandshake ||
        (state.wsConnected && (state.jobs.some(job => active(job.status)) || state.videoTasks.some(task => active(task.status))) &&
         ws.readyState === WebSocket.OPEN && Date.now() - lastUpdate > 30000))) ws.close()
  }, 15000)
}

export function disconnectWebSocket() {
  running = false
  epoch += 1
  window.clearTimeout(pollTimer)
  window.clearTimeout(reconnectTimer)
  window.clearInterval(staleTimer)
  const socket = ws
  ws = null
  if (socket) { socket.onclose = null; socket.close() }
  lastUpdate = 0
  window.removeEventListener('xyz:processing-changed',refreshProgress)
  window.removeEventListener('focus',refreshProgress)
  window.removeEventListener('online',refreshProgress)
  window.removeEventListener('pageshow',refreshProgress)
  document.removeEventListener('visibilitychange',refreshProgress)
  for(const stream of ['podcast','video'] as const){inFlight[stream]?.abort();delete inFlight[stream];lastSnapshot[stream]=0}
  useStore.getState().setWsConnected(false)
}
