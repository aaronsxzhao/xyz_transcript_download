// @vitest-environment jsdom
import React, {act, useState} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {useDialog} from '../src/lib/reading'

let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true)
  // jsdom has no layout; give rendered controls rectangles for focus testing.
  vi.spyOn(HTMLElement.prototype,'getClientRects').mockImplementation(function(this:HTMLElement){
    return (this.closest('[hidden],[style*="display: none"]')?[]:[{}]) as unknown as DOMRectList
  })
  node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.unstubAllGlobals();vi.restoreAllMocks()})

function Dialog({name,onClose}:{name:string;onClose:()=>void}){
  const ref=useDialog<HTMLDivElement>(true,onClose)
  return <div ref={ref} role="dialog" aria-label={name}>
    <button hidden>Hidden</button><button style={{display:'none'}}>Invisible</button>
    <fieldset disabled><button>Disabled by fieldset</button></fieldset>
    <button>{name} first</button><button>{name} last</button>
  </div>
}
function key(value:string,shiftKey=false){
  act(()=>document.activeElement!.dispatchEvent(new KeyboardEvent('keydown',{key:value,shiftKey,bubbles:true,cancelable:true})))
}
it('focuses the correct dialog and Escape closes only the top one, returning focus to its opener',async()=>{
  function App(){
    const [first,setFirst]=useState(false),[second,setSecond]=useState(false)
    return <><button onClick={()=>setFirst(true)}>Open first</button>
      {first&&<><Dialog name="First" onClose={()=>setFirst(false)}/><button onClick={()=>setSecond(true)}>Open second</button></>}
      {second&&<Dialog name="Second" onClose={()=>setSecond(false)}/>}</>
  }
  await act(async()=>root.render(<App/>))
  const opener=node.querySelector('button')!;opener.focus();act(()=>opener.click())
  expect(document.activeElement?.textContent).toBe('First first')
  const next=[...node.querySelectorAll('button')].find(b=>b.textContent==='Open second')!
  next.focus();act(()=>next.click())
  expect(document.activeElement?.textContent).toBe('Second first')
  key('Tab',true);expect(document.activeElement?.textContent).toBe('Second last')
  key('Tab');expect(document.activeElement?.textContent).toBe('Second first')
  key('Escape')
  expect(node.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.activeElement).toBe(next)
  key('Tab');expect(document.activeElement?.textContent).toBe('First first')
  key('Escape');expect(node.querySelector('[role="dialog"]')).toBeNull()
  expect(document.activeElement).toBe(opener)
})
it('uses the latest close callback without refocusing while dialog content updates',async()=>{
  const first=vi.fn(),latest=vi.fn()
  await act(async()=>root.render(<Dialog name="Stable" onClose={first}/>))
  const last=[...node.querySelectorAll('button')].at(-1)!;last.focus()
  await act(async()=>root.render(<Dialog name="Stable" onClose={latest}/>))
  expect(document.activeElement).toBe(last)
  key('Escape');expect(latest).toHaveBeenCalledOnce();expect(first).not.toHaveBeenCalled()
})
it('keeps focus in a loading dialog without any available controls',async()=>{
  function Empty(){const ref=useDialog<HTMLDivElement>(true,()=>{});return <div ref={ref} role="dialog">Loading</div>}
  await act(async()=>root.render(<Empty/>))
  const dialog=node.querySelector('[role="dialog"]')!
  expect(document.activeElement).toBe(dialog)
  key('Tab');expect(document.activeElement).toBe(dialog)
})
