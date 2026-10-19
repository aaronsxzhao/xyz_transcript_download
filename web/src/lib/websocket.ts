/** Account-bound real-time updates with polling when the socket is unavailable. */
import { useStore } from './store'
import { authFetch } from './api'
import { getAccessToken, refreshToken } from './auth'

let running = false
let epoch = 0
let ws: WebSocket | null = null
let pollTimer: number | undefined
let reconnectTimer: number | undefined
let staleTimer: number | undefined
let lastUpdate = 0

const active = (status: string) => !['completed', 'success', 'failed', 'cancelled', 'discovered'].includes(status)

async function pollJobs(owner: number) {
  if (!running || owner !== epoch) return
  try {
    if (document.visibilityState !== 'hidden' && !(ws?.readyState === WebSocket.OPEN && Date.now() - lastUpdate < 45000)) {
      const [jobsResponse, tasksResponse] = await Promise.all([
        authFetch('/api/jobs'), authFetch('/api/video-notes/tasks'),
      ])
      const jobs = jobsResponse.ok ? (await jobsResponse.json()).jobs : null
      const tasks = tasksResponse.ok ? (await tasksResponse.json()).tasks : null
      if (!running || owner !== epoch) return
      if (jobs) useStore.getState().mergeJobs(jobs)
      if (tasks) useStore.getState().mergeVideoTasks(tasks)
    }
  } catch (error) {
    if (running && owner === epoch) console.debug('Progress poll failed:', error)
  } finally {
    if (running && owner === epoch) {
      const state = useStore.getState()
      const busy = state.jobs.some(job => active(job.status)) || state.videoTasks.some(task => active(task.status))
      pollTimer = window.setTimeout(() => { void pollJobs(owner) }, busy ? 3000 : 15000)
    }
  }
}

function openSocket(owner: number) {
  if (!running || owner !== epoch) return
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/ws/progress`)
  ws = socket
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
  pollTimer = window.setTimeout(() => { void pollJobs(owner) }, 5000)
  openSocket(owner)
  staleTimer = window.setInterval(() => {
    const state = useStore.getState()
    if ((state.jobs.some(job => active(job.status)) || state.videoTasks.some(task => active(task.status))) &&
        ws?.readyState === WebSocket.OPEN && Date.now() - lastUpdate > 30000) ws.close()
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
  useStore.getState().setWsConnected(false)
}
