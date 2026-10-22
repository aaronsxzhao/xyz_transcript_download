// @vitest-environment jsdom
import {beforeEach,expect,it,vi} from 'vitest'
import {cancelTask} from '../src/lib/taskActions'
import {useStore} from '../src/lib/store'
import {cancelJob,cancelVideoTask} from '../src/lib/api'
vi.mock('../src/lib/api',()=>({cancelJob:vi.fn(),cancelVideoTask:vi.fn()}))
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();sessionStorage.clear();useStore.getState().reset()})

it.each(['podcast','video'] as const)('does not overwrite a completed %s with a late cancelling acknowledgement',async kind=>{
 const original={job_id:'one',status:'transcribing',progress:40,message:'Transcribing'}
 if(kind==='video')useStore.getState().setVideoTasks([{id:'one',...original} as any])
 else useStore.getState().setJobs([original])
 let finish!:(value:any)=>void
 vi.mocked(kind==='video'?cancelVideoTask:cancelJob).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=cancelTask(original,kind)
 if(kind==='video')useStore.getState().updateVideoTask({id:'one',status:'success',progress:100,message:'Complete'} as any)
 else useStore.getState().updateJob({...original,status:'completed',progress:100,message:'Complete'})
 finish({status:'cancelling'})
 await pending
 const current=kind==='video'?useStore.getState().videoTasks[0]:useStore.getState().jobs[0]
 expect(current).toMatchObject({status:kind==='video'?'success':'completed',progress:100,message:'Complete'})
})

it('does not resurrect a podcast removed while cancellation was pending',async()=>{
 const original={job_id:'one',status:'transcribing',progress:40,message:'Transcribing'}
 useStore.getState().setJobs([original])
 let finish!:(value:any)=>void
 vi.mocked(cancelJob).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=cancelTask(original,'podcast')
 useStore.getState().removeJob('one')
 finish({status:'cancelled'})
 await pending
 expect(useStore.getState().jobs).toEqual([])
})

it('retains newer progress while applying a genuine cancellation acknowledgement',async()=>{
 const original={job_id:'one',status:'transcribing',progress:40,message:'Transcribing'}
 useStore.getState().setJobs([original])
 let finish!:(value:any)=>void
 vi.mocked(cancelJob).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=cancelTask(original,'podcast')
 useStore.getState().updateJob({...original,progress:90})
 finish({status:'cancelling'})
 await pending
 expect(useStore.getState().jobs[0]).toMatchObject({status:'cancelling',progress:90})
})
