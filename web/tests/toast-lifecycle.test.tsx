// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ToastProvider,useToast} from '../src/components/Toast'

let generation=0,api:ReturnType<typeof useToast>,node:HTMLDivElement,root:ReturnType<typeof createRoot>
vi.mock('../src/lib/auth',()=>({getAuthGeneration:()=>generation}))
function Probe(){api=useToast();return null}
beforeEach(()=>{
  generation=0;vi.useFakeTimers();vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true)
  node=document.createElement('div');document.body.append(node);root=createRoot(node)
  act(()=>root.render(<ToastProvider><Probe/></ToastProvider>))
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers();vi.unstubAllGlobals()})
it('clears notifications and their timers on session changes and rejects callbacks from the previous session',()=>{
  const old=api.addToast
  act(()=>{api.addToast({type:'loading',title:'Private old task'});api.addToast({type:'error',title:'Old failure'})})
  expect(node.textContent).toContain('Private old task');expect(vi.getTimerCount()).toBe(1)
  act(()=>{generation++;window.dispatchEvent(new Event('xyz:session-changed'))})
  expect(node.querySelector('[role="alert"],[role="status"]')).toBeNull()
  expect(vi.getTimerCount()).toBe(0)
  act(()=>{expect(old({type:'error',title:'Late private response'})).toBe('')})
  expect(node.textContent).not.toContain('Late private response')
  act(()=>{api.addToast({type:'success',title:'Current task'})})
  expect(node.textContent).toContain('Current task')
})
it('releases a manually dismissed notification timer without expiring other notifications',()=>{
  let first='',second=''
  act(()=>{first=api.addToast({type:'info',title:'First',duration:500});second=api.addToast({type:'info',title:'Second',duration:2000})})
  expect(first).not.toBe(second)
  act(()=>api.removeToast(first));expect(vi.getTimerCount()).toBe(1)
  act(()=>vi.advanceTimersByTime(500));expect(node.textContent).toContain('Second')
  act(()=>vi.advanceTimersByTime(1500));expect(node.querySelector('[role="status"]')).toBeNull()
})
it('cancels outstanding timers when the notification container unmounts',()=>{
  const add=api.addToast
  act(()=>api.addToast({type:'info',title:'Temporary'}))
  expect(vi.getTimerCount()).toBe(1)
  act(()=>root.render(null));expect(vi.getTimerCount()).toBe(0)
  expect(add({type:'info',title:'Late response'})).toBe('')
})

it('expires a completed loading notification from the time of its status change',()=>{
  let id=''
  act(()=>{id=api.addToast({type:'loading',title:'Working',duration:0})})
  act(()=>vi.advanceTimersByTime(60000))
  act(()=>api.updateToast(id,{type:'success',title:'Done'}))
  expect(node.textContent).toContain('Done');expect(vi.getTimerCount()).toBe(1)
  act(()=>vi.advanceTimersByTime(4999));expect(node.textContent).toContain('Done')
  act(()=>vi.advanceTimersByTime(1));expect(node.textContent).not.toContain('Done')
})
it('does not expire a notification while it changes back to loading',()=>{
  let id=''
  act(()=>{id=api.addToast({type:'info',title:'Waiting',duration:100})})
  act(()=>api.updateToast(id,{type:'loading',title:'Working'}))
  expect(vi.getTimerCount()).toBe(0)
  act(()=>vi.advanceTimersByTime(1000));expect(node.textContent).toContain('Working')
  act(()=>node.querySelector<HTMLButtonElement>('button')!.click())
  expect(node.textContent).not.toContain('Working')
})
it('preserves an existing deadline for text updates and supports an explicit new duration',()=>{
  let id=''
  act(()=>{id=api.addToast({type:'info',title:'First',duration:1000})})
  act(()=>vi.advanceTimersByTime(900))
  act(()=>api.updateToast(id,{title:'Updated'}))
  act(()=>vi.advanceTimersByTime(100));expect(node.textContent).not.toContain('Updated')
  act(()=>{id=api.addToast({type:'loading',title:'Working'})})
  act(()=>api.updateToast(id,{type:'error',title:'Failed',duration:2000}))
  act(()=>vi.advanceTimersByTime(1999));expect(node.textContent).toContain('Failed')
  act(()=>vi.advanceTimersByTime(1));expect(node.textContent).not.toContain('Failed')
})
it('does not recreate a dismissed toast or its timer when a late update arrives',()=>{
  let id=''
  act(()=>{id=api.addToast({type:'loading',title:'Working'})})
  act(()=>api.removeToast(id))
  act(()=>api.updateToast(id,{type:'success',title:'Done'}))
  expect(vi.getTimerCount()).toBe(0);expect(node.textContent).not.toContain('Done')
})
