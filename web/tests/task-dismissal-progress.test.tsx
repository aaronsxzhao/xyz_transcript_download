// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {useStore,mergeVideoTaskPair} from '../src/lib/store'
import {taskVisible,dismissedTasks} from '../src/lib/taskPreferences'
import {setPreference} from '../src/lib/preferences'
import {useSmoothedProgress} from '../src/lib/smoothedProgress'
beforeEach(()=>{localStorage.clear();useStore.getState().reset()})
afterEach(()=>vi.restoreAllMocks())
it('keeps old acknowledgements beyond 200 entries and uses durable server state for a new attempt',()=>{
 setPreference('dismissed_tasks',JSON.stringify(Array.from({length:250},(_,i)=>`video:${i}`)))
 expect(dismissedTasks()).toHaveLength(250)
 expect(taskVisible('success','video:0')).toBe(false)
 expect(taskVisible('failed','video:0',false)).toBe(true)
 expect(taskVisible('failed','video:new',true)).toBe(false)
 expect(taskVisible('pending','video:new',true)).toBe(true)
})
it('ignores an old dismissal response after a retry and shares monotonic progress across snapshots',()=>{
 const old={id:'v',status:'failed',progress:70,task_dismissed:true,updated_at:'2026-10-31T10:00:00Z'} as any
 const queued={...old,status:'pending',progress:0,task_dismissed:false,updated_at:'2026-10-31T10:00:01Z'}
 expect(mergeVideoTaskPair(queued,old)).toMatchObject({status:'pending',progress:0,task_dismissed:false})
 const running={...queued,status:'transcribing',progress:45}
 expect(mergeVideoTaskPair(running,{...running,progress:30})).toMatchObject({progress:45})
 useStore.getState().setJobs([{job_id:'p',status:'transcribing',progress:45,revision:1} as any])
 useStore.getState().mergeJobs([{job_id:'p',status:'summarizing',progress:30,revision:2} as any])
 expect(useStore.getState().jobs[0].progress).toBe(45)
 useStore.getState().updateJob({job_id:'p',status:'pending',progress:0,revision:3} as any)
 expect(useStore.getState().jobs[0].progress).toBe(0)
})
it('interpolates only toward reported progress and cancels animation when unmounted',()=>{
 let callback:FrameRequestCallback=()=>{};let now=0
 vi.spyOn(performance,'now').mockImplementation(()=>now)
 vi.stubGlobal('requestAnimationFrame',vi.fn(fn=>{callback=fn;return 1}))
 const cancel=vi.fn();vi.stubGlobal('cancelAnimationFrame',cancel)
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 function Meter({value}:{value:number}){return <span>{useSmoothedProgress(value,'attempt')}</span>}
 try{
  act(()=>root.render(<Meter value={20}/>))
  act(()=>root.render(<Meter value={60}/>))
  // RAF timestamps can predate an effect started in the same frame.
  act(()=>callback(-1));expect(Number(node.textContent)).toBe(20)
  now=300;act(()=>callback(now))
  expect(Number(node.textContent)).toBeGreaterThan(20);expect(Number(node.textContent)).toBeLessThan(60)
  now=900;act(()=>callback(now));expect(Number(node.textContent)).toBe(60)
  act(()=>root.unmount());expect(cancel).toHaveBeenCalled()
 }finally{node.remove();vi.unstubAllGlobals()}
})
it('keeps 45% when a poll omits the worker start time and a later event reports 19%',()=>{
 const base={id:'v',status:'transcribing',progress:19,started_at:100,updated_at:'2026-11-02T10:00:00Z'} as any
 useStore.getState().updateVideoTask(base)
 useStore.getState().updateVideoTask({...base,progress:45,updated_at:'2026-11-02T10:00:01Z'})
 useStore.getState().mergeVideoTasks([{...base,progress:19,started_at:0,updated_at:'2026-11-02T10:00:02Z'}])
 useStore.getState().updateVideoTask({...base,updated_at:'2026-11-02T10:00:03Z'})
 expect(useStore.getState().videoTasks[0]).toMatchObject({progress:45,started_at:100})
})
it('does not let stale start metadata contaminate a newer attempt',()=>{
 const current={id:'v',status:'transcribing',progress:19,started_at:200,updated_at:'2026-11-02T10:00:03Z'} as any
 const stale={...current,progress:45,started_at:100,updated_at:'2026-11-02T10:00:01Z'}
 expect(mergeVideoTaskPair(current,stale)).toMatchObject({progress:19,started_at:200})
 const later={...current,progress:30,updated_at:'2026-11-02T10:00:04Z'}
 expect(mergeVideoTaskPair(mergeVideoTaskPair(current,stale),later)).toMatchObject({progress:30,started_at:200})
})
it('learning a previously missing start time is not a retry; actual retries reset',()=>{
 const current={id:'v',status:'transcribing',progress:45,started_at:0,updated_at:'2026-11-02T10:00:00Z'} as any
 const learned={...current,progress:19,started_at:100,updated_at:'2026-11-02T10:00:01Z'}
 expect(mergeVideoTaskPair(current,learned)).toMatchObject({progress:45,started_at:100})
 expect(mergeVideoTaskPair({...current,started_at:100},{...learned,started_at:200})).toMatchObject({progress:19,started_at:200})
 const queued={...learned,status:'pending',progress:0,started_at:0}
 expect(mergeVideoTaskPair(current,queued)).toMatchObject({progress:0,started_at:0})
})
