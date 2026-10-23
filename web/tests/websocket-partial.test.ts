// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
const api=vi.hoisted(()=>({authFetch:vi.fn(),fetchProgress:vi.fn()}))
vi.mock('../src/lib/api',()=>api)
vi.mock('../src/lib/auth',()=>({getAccessToken:()=>null,refreshToken:vi.fn()}))
import {connectWebSocket,disconnectWebSocket} from '../src/lib/websocket'
import {useStore} from '../src/lib/store'

class Socket {
  static OPEN=1
  static current: Socket
  onmessage?: (event: {data:string}) => void
  readyState=1
  close=vi.fn()
  constructor(){Socket.current=this}
}
const completedJob={job_id:'podcast',status:'completed',progress:100}
const completedVideo={id:'video',status:'success',progress:100}
beforeEach(()=>{
  vi.useFakeTimers();vi.clearAllMocks();useStore.getState().reset()
  vi.stubGlobal('WebSocket',Socket)
  vi.spyOn(document,'visibilityState','get').mockReturnValue('visible')
  api.authFetch.mockResolvedValue({ok:true,json:async()=>({jobs:[completedJob]})})
  api.fetchProgress.mockResolvedValue({tasks:[completedVideo]})
})
afterEach(()=>{disconnectWebSocket();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals()})

it('applies podcast progress even when the video progress endpoint fails',async()=>{
  api.fetchProgress.mockRejectedValue(new TypeError('Video connection interrupted'))
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  expect(useStore.getState().jobs).toContainEqual(completedJob)
})

it.each(['network','json','http'])('applies video progress when podcast polling has a %s failure',async failure=>{
  if(failure==='network')api.authFetch.mockRejectedValue(new TypeError('Podcast connection interrupted'))
  if(failure==='json')api.authFetch.mockResolvedValue({ok:true,json:async()=>{throw new SyntaxError('Truncated response')}})
  if(failure==='http')api.authFetch.mockResolvedValue({ok:false})
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  expect(useStore.getState().videoTasks).toContainEqual(completedVideo)
})

it('does not apply either late poll result after disconnecting for an account change',async()=>{
  let finish!:(value:unknown)=>void
  api.fetchProgress.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  disconnectWebSocket();useStore.getState().reset()
  finish({tasks:[completedVideo]});await vi.advanceTimersByTimeAsync(0)
  expect(useStore.getState().jobs).toEqual([])
  expect(useStore.getState().videoTasks).toEqual([])
})

it.each(['podcast','video'])('updates %s progress without waiting for a slow counterpart',async kind=>{
  let finish!:(value:any)=>void
  if(kind==='podcast')api.fetchProgress.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  else api.authFetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  try {
    if(kind==='podcast')expect(useStore.getState().jobs).toContainEqual(completedJob)
    else expect(useStore.getState().videoTasks).toContainEqual(completedVideo)
  } finally {
    finish(kind==='podcast'?{tasks:[]}:{ok:true,json:async()=>({jobs:[]})})
    await vi.advanceTimersByTimeAsync(0)
  }
})

it('keeps websocket completion when an older HTTP poll finishes afterward',async()=>{
  let finish!:(value:any)=>void
  api.authFetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  Socket.current.onmessage?.({data:JSON.stringify({type:'job_update',job:{...completedJob,revision:2}})})
  finish({ok:true,json:async()=>({jobs:[{...completedJob,status:'transcribing',progress:40,revision:1}]})})
  await vi.advanceTimersByTimeAsync(0)
  expect(useStore.getState().jobs[0]).toMatchObject({status:'completed',progress:100,revision:2})
})
