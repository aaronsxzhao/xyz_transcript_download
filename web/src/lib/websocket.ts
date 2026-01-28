/**
 * WebSocket client for real-time updates with polling fallback
 */
import { useStore } from './store'
import type { ProcessingJob } from './api'

let ws: WebSocket | null = null
let reconnectTimeout: number | null = null
let pollInterval: number | null = null

// Poll for job updates as fallback (every 2 seconds when there are active jobs)
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
    }
  } catch (e) {
    // Silently fail - polling is just a fallback
  }
}

function startPolling() {
  if (pollInterval) return
  
  // Poll immediately, then every 2 seconds
  pollJobs()
  pollInterval = window.setInterval(() => {
    // Only poll if there are active jobs
    const jobs = useStore.getState().jobs
    const hasActiveJobs = jobs.some(job => 
      !['completed', 'failed', 'cancelled'].includes(job.status)
    )
    
    if (hasActiveJobs) {
      pollJobs()
    }
  }, 2000)
}

function stopPolling() {
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
