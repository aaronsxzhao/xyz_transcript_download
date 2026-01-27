/**
 * WebSocket client for real-time updates
 */
import { useStore } from './store'

let ws: WebSocket | null = null
let reconnectTimeout: number | null = null

export function connectWebSocket() {
  if (ws?.readyState === WebSocket.OPEN) return
  
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
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
  }
  if (ws) {
    ws.close()
    ws = null
  }
}
