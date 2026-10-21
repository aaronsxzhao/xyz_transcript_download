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

it('uses socket heartbeats to avoid redundant idle database polls', async () => {
  connectWebSocket()
  const socket = FakeSocket.instances[0]
  socket.onmessage!({ data: JSON.stringify({ type: 'init', jobs: [], video_tasks: [] }) })
  for (let i = 0; i < 8; i++) {
    await vi.advanceTimersByTimeAsync(15000)
    socket.onmessage!({ data: JSON.stringify({ type: 'heartbeat' }) })
  }
  expect(fetch).not.toHaveBeenCalled()
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
  expect(fetch).toHaveBeenCalledTimes(2)
  vi.restoreAllMocks()
})
