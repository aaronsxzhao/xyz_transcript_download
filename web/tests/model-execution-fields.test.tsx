// @vitest-environment jsdom
import React,{act,useState} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import ModelExecutionFields from '../src/components/ModelExecutionFields'
import {clearTokens} from '../src/lib/auth'
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{clearTokens();vi.useFakeTimers();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers();vi.unstubAllGlobals()})
function Host({model='openai/gpt-oss-120b'}:{model?:string}){
 const [value,setValue]=useState({llm_reasoning_effort:'',llm_service_tier:''})
 return <ModelExecutionFields provider="groq" model={model} baseUrl="" value={value} onChange={setValue} disabled={false}/>
}
it('offers only reported capabilities and retains the selected reasoning and service values',async()=>{
 const fetch=vi.fn().mockResolvedValue(Response.json({reasoning:['low','medium','high'],tiers:['auto','performance'],known:true}));vi.stubGlobal('fetch',fetch)
 await act(async()=>{root.render(<Host/>)});await act(async()=>vi.advanceTimersByTimeAsync(400))
 const select=node.querySelector<HTMLSelectElement>('[aria-label="Reasoning effort"]')!
 expect([...select.options].map(o=>o.value)).toEqual(['','low','medium','high'])
 act(()=>{select.value='high';select.dispatchEvent(new Event('change',{bubbles:true}))})
 expect(select.value).toBe('high')
 expect(JSON.parse(fetch.mock.calls[0][1].body).llm_model).toBe('openai/gpt-oss-120b')
})
it('does not describe an unknown gateway as verified support',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({reasoning:['low','high'],tiers:['priority'],known:false})))
 await act(async()=>root.render(<Host model="custom-model"/>));await act(async()=>vi.advanceTimersByTimeAsync(400))
 expect(node.textContent).toContain('does not publish verified capabilities')
 expect(node.textContent).toContain('flex is not a universal fast mode')
})
it('reports failed capability loading without resetting saved selections',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('Unavailable',{status:503})))
 await act(async()=>root.render(<ModelExecutionFields provider="custom" model="custom" baseUrl="https://example.org/v1" value={{llm_reasoning_effort:'high',llm_service_tier:''}} onChange={()=>{}} disabled={false}/>))
 await act(async()=>vi.advanceTimersByTimeAsync(400))
 expect(node.textContent).toContain('Cannot read model options')
 expect(node.querySelector<HTMLSelectElement>('[aria-label="Reasoning effort"]')!.value).toBe('high')
})
