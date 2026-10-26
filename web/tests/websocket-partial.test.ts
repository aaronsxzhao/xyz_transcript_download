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

it.each(['podcast','video'] as const)('does not restore a deleted %s from an in-flight progress poll',async kind=>{
  let finish!:(value:any)=>void
  if(kind==='podcast')api.authFetch.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  else api.fetchProgress.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
  if(kind==='podcast'){
    useStore.getState().removeJob('podcast')
    finish({ok:true,json:async()=>({jobs:[completedJob]})})
  }else{
    useStore.getState().removeVideoTask('video')
    finish({tasks:[completedVideo]})
  }
  await vi.advanceTimersByTimeAsync(0)
  expect(kind==='podcast'?useStore.getState().jobs:useStore.getState().videoTasks).toEqual([])
})

it('keeps reconciling videos while podcast websocket updates arrive continuously',async()=>{
 connectWebSocket()
 Socket.current.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[{...completedVideo,status:'pending'}]})})
 for(let i=0;i<6;i++){
  Socket.current.onmessage?.({data:JSON.stringify({type:'job_update',job:{job_id:'other',status:'transcribing',revision:i,created_at:Date.now()/1000}})})
  await vi.advanceTimersByTimeAsync(2000)
 }
 expect(api.fetchProgress).toHaveBeenCalled()
 expect(useStore.getState().videoTasks[0].status).toBe('success')
})

it('keeps podcast reconciliation running while the video request never finishes',async()=>{
 api.fetchProgress.mockImplementation(()=>new Promise(()=>{}))
 useStore.getState().updateVideoTask({...completedVideo,status:'pending'} as any)
 connectWebSocket()
 await vi.advanceTimersByTimeAsync(18000)
 expect(api.authFetch.mock.calls.length).toBeGreaterThan(1)
 expect(api.fetchProgress).toHaveBeenCalledOnce()
})

it('discovers completed work even when an idle websocket only sends heartbeats',async()=>{
 connectWebSocket()
 Socket.current.onmessage?.({data:JSON.stringify({type:'init',jobs:[],video_tasks:[]})})
 for(let i=0;i<4;i++){
  Socket.current.onmessage?.({data:JSON.stringify({type:'heartbeat'})})
  await vi.advanceTimersByTimeAsync(10000)
 }
 expect(useStore.getState().videoTasks).toContainEqual(completedVideo)
})

it('refreshes immediately after admission and ignores reads that began before it',async()=>{
 let finish!:(value:any)=>void
 api.fetchProgress.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 useStore.getState().updateVideoTask({...completedVideo,status:'pending'} as any)
 connectWebSocket();await vi.advanceTimersByTimeAsync(5000)
 window.dispatchEvent(new Event('xyz:processing-changed'))
 await vi.advanceTimersByTimeAsync(1)
 expect(useStore.getState().videoTasks[0].status).toBe('success')
 finish({tasks:[{...completedVideo,status:'pending'}]});await vi.advanceTimersByTimeAsync(0)
 expect(useStore.getState().videoTasks[0].status).toBe('success')
})

it('bounds a stalled podcast JSON body and ignores its eventual stale response',async()=>{
 let finish!:(value:any)=>void
 api.authFetch.mockResolvedValueOnce({ok:true,json:()=>new Promise(resolve=>{finish=resolve})})
 useStore.getState().updateJob({...completedJob,status:'pending',created_at:Date.now()/1000} as any)
 connectWebSocket();await vi.advanceTimersByTimeAsync(21000)
 expect(useStore.getState().jobs[0].status).toBe('completed')
 finish({jobs:[{...completedJob,status:'pending'}]});await vi.advanceTimersByTimeAsync(0)
 expect(useStore.getState().jobs[0].status).toBe('completed')
})
