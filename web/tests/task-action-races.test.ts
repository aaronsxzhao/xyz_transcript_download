// @vitest-environment jsdom
import {beforeEach,expect,it,vi} from 'vitest'
import {cancelTask,retryTask} from '../src/lib/taskActions'
import {useStore} from '../src/lib/store'
import {cancelJob,cancelVideoTask,retryJob,retryVideoTask,fetchJob} from '../src/lib/api'
vi.mock('../src/lib/api',()=>({cancelJob:vi.fn(),cancelVideoTask:vi.fn(),retryJob:vi.fn(),retryVideoTask:vi.fn(),fetchJob:vi.fn()}))
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

it.each(['transcribing','success'] as const)('keeps newer video %s state when retry acknowledgement arrives late',async status=>{
 const original={job_id:'one',status:'failed',progress:0,message:'Failed'}
 useStore.getState().setVideoTasks([{id:'one',...original,updated_at:'2026-10-22T10:00:00Z'} as any])
 let finish!:(value:any)=>void
 vi.mocked(retryVideoTask).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const pending=retryTask(original,'video')
 useStore.getState().updateVideoTask({id:'one',status,progress:status==='success'?100:40,message:'New attempt',updated_at:'2026-10-22T10:00:01Z'} as any)
 finish({task_id:'one'})
 await pending
 expect(useStore.getState().videoTasks[0]).toMatchObject({status,progress:status==='success'?100:40,message:'New attempt'})
})

it('keeps websocket progress for a new podcast job before its retry response and reconciliation finish',async()=>{
 const original={job_id:'old',episode_id:'episode',status:'failed',progress:0,message:'Failed'}
 useStore.getState().setJobs([original])
 let finish!:(value:any)=>void
 vi.mocked(retryJob).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(fetchJob).mockImplementationOnce(()=>new Promise(()=>{}))
 const pending=retryTask(original,'podcast')
 useStore.getState().updateJob({job_id:'new',status:'summarizing',progress:80,message:'Writing notes'})
 finish({new_job_id:'new',message:'Retry started'})
 await pending
 expect(useStore.getState().jobs.find(j=>j.job_id==='new')).toMatchObject({status:'summarizing',progress:80,message:'Writing notes'})
})

it('does not overwrite podcast completion with a stale retry reconciliation fetch',async()=>{
 const original={job_id:'old',status:'failed',progress:0,message:'Failed'}
 useStore.getState().setJobs([original])
 vi.mocked(retryJob).mockResolvedValueOnce({new_job_id:'new',message:'Retry started'})
 let finish!:(value:any)=>void
 vi.mocked(fetchJob).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await retryTask(original,'podcast')
 useStore.getState().updateJob({job_id:'new',status:'completed',progress:100,message:'Complete'})
 finish({job_id:'new',status:'transcribing',progress:30,message:'Older response'})
 await Promise.resolve()
 expect(useStore.getState().jobs.find(j=>j.job_id==='new')).toMatchObject({status:'completed',progress:100,message:'Complete'})
})
