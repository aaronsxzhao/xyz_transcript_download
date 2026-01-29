/**
 * WebSocket client for real-time updates with polling fallback
 */
import { useStore } from './store'
import type { ProcessingJob } from './api'

let ws: WebSocket | null = null
let reconnectTimeout: number | null = null
let pollInterval: number | null = null
let fastPollInterval: number | null = null

// Poll for job updates as fallback
async function pollJobs() {
  try {
    const response = await fetch('/api/jobs')
    if (response.ok) {
      const data = await response.json()
      const jobs: ProcessingJob[] = data.jobs || []
      
      // Update each job in the store
      jobs.forEach(job => {
        useStore.getState().updateJob(job)
      })
      
      // Manage fast polling based on active jobs
      const hasActiveJobs = jobs.some(job => 
        !['completed', 'failed', 'cancelled'].includes(job.status)
      )
      
      if (hasActiveJobs && !fastPollInterval) {
        startFastPolling()
      } else if (!hasActiveJobs && fastPollInterval) {
        stopFastPolling()
      }
    }
  } catch (e) {
    // Silently fail - polling is just a fallback
  }
}

// Fast polling (every 500ms) for smooth progress updates during active jobs
function startFastPolling() {
  if (fastPollInterval) return
  
  fastPollInterval = window.setInterval(() => {
    pollJobs()
  }, 500)
}

function stopFastPolling() {
  if (fastPollInterval) {
    clearInterval(fastPollInterval)
    fastPollInterval = null
  }
}

function startPolling() {
  if (pollInterval) return
  
  // Poll immediately, then every 3 seconds for checking new jobs
  pollJobs()
  pollInterval = window.setInterval(() => {
    pollJobs()
  }, 3000)
}

function stopPolling() {
  stopFastPolling()
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

export function connectWebSocket() {
  if (ws?.readyState === WebSocket.OPEN) return
  
  // Start polling as fallback
  startPolling()
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // Use current host and port (works for both dev and production)
  const wsUrl = `${protocol}//${window.location.host}/api/ws/progress`
  
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('WebSocket connected')
    useStore.getState().setWsConnected(true)
  }
  
  ws.onclose = () => {
    console.log('WebSocket disconnected')
    useStore.getState().setWsConnected(false)
    
    // Reconnect after 3 seconds
    reconnectTimeout = window.setTimeout(() => {
      connectWebSocket()
    }, 3000)
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      
      switch (data.type) {
        case 'init':
          useStore.getState().setJobs(data.jobs || [])
          break
        
        case 'job_update':
          if (data.job) {
            useStore.getState().updateJob(data.job)
          }
          break
        
        case 'heartbeat':
          // Send pong
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
