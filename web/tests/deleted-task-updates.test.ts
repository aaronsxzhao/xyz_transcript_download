// @vitest-environment jsdom
import {beforeEach,expect,it} from 'vitest'
import {useStore} from '../src/lib/store'
import type {VideoTask} from '../src/lib/api'

const podcast={job_id:'deleted',status:'transcribing',progress:40,message:'Working',revision:1}
const video={id:'deleted',status:'transcribing',progress:40,message:'Working',updated_at:'2026-10-23T08:00:00Z'} as VideoTask
beforeEach(()=>useStore.getState().reset())

it.each(['podcast','video'] as const)('ignores late list and websocket updates after deleting a %s task',kind=>{
  const state=useStore.getState()
  if(kind==='podcast'){
    state.updateJob(podcast)
    state.removeJob('deleted')
    state.mergeJobs([podcast])
    state.updateJob({...podcast,revision:2,status:'completed',progress:100})
    expect(useStore.getState().jobs).toEqual([])
  }else{
    state.updateVideoTask(video)
    state.removeVideoTask('deleted')
    state.mergeVideoTasks([video])
    state.updateVideoTask({...video,status:'success',progress:100,updated_at:'2026-10-23T08:00:01Z'})
    expect(useStore.getState().videoTasks).toEqual([])
  }
})

it.each(['podcast','video'] as const)('also filters an older full %s snapshot without blocking unrelated tasks',kind=>{
  const state=useStore.getState()
  if(kind==='podcast'){
    state.removeJob('deleted')
    state.setJobs([podcast,{...podcast,job_id:'other'}])
    expect(useStore.getState().jobs.map(row=>row.job_id)).toEqual(['other'])
  }else{
    state.removeVideoTask('deleted')
    state.setVideoTasks([video,{...video,id:'other'}])
    expect(useStore.getState().videoTasks.map(row=>row.id)).toEqual(['other'])
  }
})

it.each(['podcast','video'] as const)('clears %s deletion markers when resetting the account',kind=>{
  const state=useStore.getState()
  state.removeJob('deleted');state.removeVideoTask('deleted')
  state.reset()
  if(kind==='podcast'){
    state.mergeJobs([podcast])
    expect(useStore.getState().jobs).toEqual([podcast])
  }else{
    state.mergeVideoTasks([video])
    expect(useStore.getState().videoTasks[0].id).toBe('deleted')
  }
})

it('expires only unconfirmed local jobs while preserving acknowledged and newly submitted work',()=>{
 const now=Date.now()/1000,state=useStore.getState()
 state.setJobs([
  {...podcast,job_id:'stale',status:'pending',created_at:now-60},
  {...podcast,job_id:'fresh',status:'pending',created_at:now-2},
  {...podcast,job_id:'acknowledged',status:'pending',created_at:now-120},
 ])
 state.mergeJobs([{...podcast,job_id:'acknowledged',status:'pending',created_at:now-120}])
 expect(useStore.getState().jobs.map(job=>job.job_id).sort()).toEqual(['acknowledged','fresh'])
})
