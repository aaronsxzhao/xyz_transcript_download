/**
 * WebSocket client for real-time updates with polling fallback
 * 
 * Connected once at app startup (main.tsx), never tied to component lifecycle.
 * This avoids React StrictMode double-mount issues entirely.
 */
import { useStore } from './store'
import { authFetch, type ProcessingJob } from './api'
import { getAccessToken } from './auth'

function isActiveVideoStatus(status: string): boolean {
  return !['success', 'failed', 'cancelled', 'discovered'].includes(status)
}

let ws: WebSocket | null = null
let pollInterval: number | null = null
let wsWorking = false
let lastMessageTime = 0
/** Set on socket open; used when no message was ever received (lastMessageTime still 0). */
let wsOpenTime = 0
let staleCheckInterval: number | null = null
let connected = false

async function pollJobs() {
  if (wsWorking && ws?.readyState === WebSocket.OPEN) {
    return
  }
  
  try {
    const [jobsResponse, videoTasksResponse] = await Promise.all([
      authFetch('/api/jobs'),
      authFetch('/api/video-notes/tasks'),
    ])

    let stillHasActiveJobs = false
    let stillHasActiveVideoTasks = false

    if (jobsResponse.ok) {
      const data = await jobsResponse.json()
      const serverJobs: ProcessingJob[] = data.jobs || []

      serverJobs.forEach(job => {
        useStore.getState().updateJob(job)
      })

      stillHasActiveJobs = serverJobs.some(job =>
        !['completed', 'failed', 'cancelled'].includes(job.status)
      )
    }

    if (videoTasksResponse.ok) {
      const data = await videoTasksResponse.json()
      const serverTasks = data.tasks || []
      useStore.getState().mergeVideoTasks(serverTasks)
      stillHasActiveVideoTasks = serverTasks.some((task: { status: string }) =>
        isActiveVideoStatus(task.status)
      )
    }

    const desiredInterval = (stillHasActiveJobs || stillHasActiveVideoTasks) ? 3000 : 15000
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = window.setInterval(pollJobs, desiredInterval)
    }
  } catch (e) {
    console.debug('Poll failed:', e)
  }
}

function startPolling() {
  if (pollInterval) return
  pollJobs()
  pollInterval = window.setInterval(pollJobs, 5000)
}

export function connectWebSocket() {
  if (connected) return
  connected = true

  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return
  
  startPolling()
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/ws/progress`
  
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    wsOpenTime = Date.now()
    console.log('WebSocket connected')
    useStore.getState().setWsConnected(true)
    
    const token = getAccessToken()
    if (token && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'auth', token }))
    } else if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'auth' }))
    }
  }
  
  ws.onclose = () => {
    console.log('WebSocket disconnected')
    useStore.getState().setWsConnected(false)
    wsWorking = false
    
    window.setTimeout(() => {
      connected = false
      connectWebSocket()
    }, 3000)
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
    wsWorking = false
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      lastMessageTime = Date.now()
      
      switch (data.type) {
        case 'init':
          console.log('WebSocket init:', data.jobs?.length || 0, 'jobs')
          useStore.getState().mergeJobs(data.jobs || [])
          if (data.video_tasks?.length) {
            useStore.getState().mergeVideoTasks(data.video_tasks)
          }
          break
        
        case 'job_update':
          if (data.job) {
            wsWorking = true
            useStore.getState().updateJob(data.job)
          }
          break
        
        case 'video_job_update':
          if (data.task) {
            wsWorking = true
            useStore.getState().updateVideoTask(data.task)
          }
          break
        
        case 'heartbeat':
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
          break
      }
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e)
    }
  }
  
  if (staleCheckInterval) clearInterval(staleCheckInterval)
  staleCheckInterval = window.setInterval(() => {
    const jobs = useStore.getState().jobs
    const hasActiveJobs = jobs.some(job => 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
    
    const lastActivity = lastMessageTime > 0 ? lastMessageTime : wsOpenTime
    const trustWs =
      lastMessageTime > 0 ? wsWorking : true
    if (
      hasActiveJobs &&
      trustWs &&
      lastActivity > 0 &&
      Date.now() - lastActivity > 30000
    ) {
      console.log('WebSocket appears stale (no message for 30s), reconnecting...')
      wsWorking = false
      ws?.close()
    }
  }, 15000)
}
