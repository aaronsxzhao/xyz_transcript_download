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

// Poll for job updates (fallback when WebSocket fails)
async function pollJobs() {
  // Skip polling if WebSocket is working
  if (wsWorking && ws?.readyState === WebSocket.OPEN) {
    return
  }
  
  try {
    const response = await authFetch('/api/jobs')
    if (response.ok) {
      const data = await response.json()
      const jobs: ProcessingJob[] = data.jobs || []
      
      // Update each job in the store
      jobs.forEach(job => {
        useStore.getState().updateJob(job)
      })
      
      // Adjust polling speed based on active jobs
      const hasActiveJobs = jobs.some(job => 
        !['completed', 'failed', 'cancelled'].includes(job.status)
      )
      
      // Switch between fast (1s) and slow (5s) polling
      const desiredInterval = hasActiveJobs ? 1000 : 5000
      if (pollInterval) {
        // Update interval if needed by restarting
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
      
      // Mark WebSocket as working on first successful message
      if (!wsWorking) {
        wsWorking = true
        console.log('WebSocket receiving updates, polling paused')
      }
      
      switch (data.type) {
        case 'init':
          useStore.getState().mergeJobs(data.jobs || [])
          break
        
        case 'job_update':
          if (data.job) {
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
}

export function disconnectWebSocket() {
  stopPolling()
  
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
  }
  if (ws) {
    ws.close()
    ws = null
  }
}
