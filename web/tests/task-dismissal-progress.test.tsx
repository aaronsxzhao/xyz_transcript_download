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
  now=300;act(()=>callback(now))
  expect(Number(node.textContent)).toBeGreaterThan(20);expect(Number(node.textContent)).toBeLessThan(60)
  now=600;act(()=>callback(now));expect(Number(node.textContent)).toBe(60)
  act(()=>root.unmount());expect(cancel).toHaveBeenCalled()
 }finally{node.remove();vi.unstubAllGlobals()}
})
