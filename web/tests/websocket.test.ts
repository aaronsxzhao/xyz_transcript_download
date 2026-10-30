// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { connectWebSocket, disconnectWebSocket } from '../src/lib/websocket'
import { useStore } from '../src/lib/store'

class FakeSocket {
  static OPEN = 1
  static instances: FakeSocket[] = []
  readyState = 1
  onopen: (() => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  send = vi.fn()
  close = vi.fn()
  constructor(_url: string) { FakeSocket.instances.push(this) }
}

beforeEach(() => {
  vi.useFakeTimers()
  useStore.getState().reset()
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => Response.json(url.endsWith('/jobs') ? { jobs: [] } : { tasks: [] })))
})
afterEach(() => { disconnectWebSocket(); vi.useRealTimers(); vi.unstubAllGlobals() })

it('disconnects without scheduling reconnections or leaving polling active', async () => {
  connectWebSocket()
  await vi.advanceTimersByTimeAsync(1)
  const socket = FakeSocket.instances[0]
  disconnectWebSocket()
  await vi.advanceTimersByTimeAsync(60000)
  expect(socket.close).toHaveBeenCalledOnce()
  expect(FakeSocket.instances).toHaveLength(1)
  expect(useStore.getState().wsConnected).toBe(false)
})

it('ignores late progress messages from the previous account', () => {
  connectWebSocket()
  const oldMessage = FakeSocket.instances[0].onmessage!
  disconnectWebSocket()
  connectWebSocket()
  oldMessage({ data: JSON.stringify({ type: 'job_update', job: { job_id: 'private-old-job', status: 'pending' } }) })
  expect(useStore.getState().jobs).toEqual([])
  expect(FakeSocket.instances).toHaveLength(2)
})

it('bounds idle snapshots even when the socket only sends heartbeats', async () => {
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  socket.onmessage!({ data: JSON.stringify({ type: 'init', jobs: [], video_tasks: [] }) })
  for (let i = 0; i < 8; i++) {
    await vi.advanceTimersByTimeAsync(15000)
    socket.onmessage!({ data: JSON.stringify({ type: 'heartbeat' }) })
  }
  expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(0)
  expect(vi.mocked(fetch).mock.calls.length).toBeLessThanOrEqual(8)
})

it('reconciles active jobs when a completion event was missed', async () => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => Response.json(url.endsWith('/jobs')
    ? { jobs: [{ job_id: 'quiet-job', status: 'completed' }] } : { tasks: [] })))
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  socket.onmessage!({ data: JSON.stringify({ type: 'init', jobs: [{ job_id: 'quiet-job', status: 'pending' }], video_tasks: [] }) })
  for (let i = 0; i < 3; i++) {
    await vi.advanceTimersByTimeAsync(3000)
    socket.onmessage!({ data: JSON.stringify({ type: 'heartbeat' }) })
  }
  expect(useStore.getState().jobs.find(job => job.job_id === 'quiet-job')?.status).toBe('completed')
  expect(fetch).toHaveBeenCalledOnce()
  vi.restoreAllMocks()
})

it('reconnects a stalled handshake even when there are no active tasks', async () => {
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  socket.readyState = 0
  socket.close.mockImplementation(() => {
    socket.readyState = 3
    socket.onclose?.({code:1006})
  })
  await vi.advanceTimersByTimeAsync(30000)
  expect(socket.close).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(18000)
  expect(socket.close).toHaveBeenCalledOnce()
  expect(FakeSocket.instances).toHaveLength(2)
})

it('does not close an initialized idle connection at the handshake deadline', async () => {
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  socket.onmessage!({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})})
  await vi.advanceTimersByTimeAsync(60000)
  expect(socket.close).not.toHaveBeenCalled()
})

it('gives an active task connection its full initialization grace period', async () => {
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  vi.stubGlobal('fetch',vi.fn(async (url: string) => Response.json(url.endsWith('/jobs')
    ? {jobs:[{job_id:'active',status:'transcribing',progress:10}]} : {tasks:[]})))
  await vi.advanceTimersByTimeAsync(30000)
  expect(useStore.getState().jobs[0]?.status).toBe('transcribing')
  expect(socket.close).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(15000)
  expect(socket.close).toHaveBeenCalledOnce()
})
