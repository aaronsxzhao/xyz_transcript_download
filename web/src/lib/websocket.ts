/**
 * WebSocket client for real-time updates with polling fallback
 * 
 * Strategy:
 * - WebSocket is primary for real-time updates
 * - Polling is fallback only when WebSocket fails
 * - Only ONE polling interval runs at a time (fast OR regular, not both)
 */
import { useStore } from './store'
import { authFetch, type ProcessingJob } from './api'

let ws: WebSocket | null = null
let reconnectTimeout: number | null = null
let pollInterval: number | null = null
let wsWorking = false  // Track if WebSocket is successfully receiving updates
let lastMessageTime = 0  // Track last message for stale connection detection
let staleCheckInterval: number | null = null

// Poll for job updates (fallback when WebSocket fails)
async function pollJobs() {
  // Skip polling entirely if WebSocket is working
  // Stale connection detection (30s timeout) handles WebSocket failures
  if (wsWorking && ws?.readyState === WebSocket.OPEN) {
    return
  }
  
  try {
    const response = await authFetch('/api/jobs')
    if (response.ok) {
      const data = await response.json()
      const serverJobs: ProcessingJob[] = data.jobs || []
      
      // Update each job in the store
      serverJobs.forEach(job => {
        useStore.getState().updateJob(job)
      })
      
      // Check if any jobs are active after update
      const stillHasActiveJobs = serverJobs.some(job => 
        !['completed', 'failed', 'cancelled'].includes(job.status)
      )
      
      // Poll faster (3s) if there are active jobs and WebSocket is down
      // Otherwise slow poll (15s) to check for new jobs
      const desiredInterval = stillHasActiveJobs ? 3000 : 15000
      if (pollInterval) {
        clearInterval(pollInterval)
        pollInterval = window.setInterval(pollJobs, desiredInterval)
      }
    }
  } catch (e) {
    console.debug('Poll failed:', e)
  }
}

function startPolling() {
  if (pollInterval) return
  
  // Start with slow polling (5s), will speed up if active jobs detected
  pollJobs()
  pollInterval = window.setInterval(pollJobs, 5000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

export function connectWebSocket() {
  if (ws?.readyState === WebSocket.OPEN) return
  
  // Start polling as fallback (will stop if WebSocket works)
  startPolling()
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/ws/progress`
  
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('WebSocket connected')
    useStore.getState().setWsConnected(true)
  }
  
  ws.onclose = () => {
    console.log('WebSocket disconnected')
    useStore.getState().setWsConnected(false)
    wsWorking = false
    
    // Reconnect after 3 seconds
    reconnectTimeout = window.setTimeout(() => {
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
      
      // Mark WebSocket as working on first successful message
      if (!wsWorking) {
        wsWorking = true
        console.log('WebSocket receiving updates, polling paused')
      }
      
      switch (data.type) {
        case 'init':
          console.log('WebSocket init:', data.jobs?.length || 0, 'jobs')
          useStore.getState().mergeJobs(data.jobs || [])
          break
        
        case 'job_update':
          if (data.job) {
            console.log('WebSocket job_update:', data.job.job_id, data.job.progress?.toFixed(1) + '%')
            useStore.getState().updateJob(data.job)
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
  
  // Check for stale connection every 15 seconds
  // If we have active jobs but no message for 30s, reconnect
  if (staleCheckInterval) clearInterval(staleCheckInterval)
  staleCheckInterval = window.setInterval(() => {
    const jobs = useStore.getState().jobs
    const hasActiveJobs = jobs.some(job => 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
    
    if (hasActiveJobs && wsWorking && lastMessageTime > 0) {
      const timeSinceLastMessage = Date.now() - lastMessageTime
      if (timeSinceLastMessage > 30000) {
        console.log('WebSocket appears stale (no message for 30s), reconnecting...')
        wsWorking = false
        ws?.close()
      }
    }
  }, 15000)
}

export function disconnectWebSocket() {
  stopPolling()
  
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
    reconnectTimeout = null
  }
  if (staleCheckInterval) {
    clearInterval(staleCheckInterval)
    staleCheckInterval = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  wsWorking = false
  lastMessageTime = 0
}
