// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {MoreReaderActions,RegenerateAction} from '../src/components/ReaderChrome'
import {readingIntersection} from '../src/lib/readingIntersection'
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true)
 vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.restoreAllMocks();vi.unstubAllGlobals()})
it.each(['Cancel','Escape','Regenerate'])('keeps the confirmation outside its menu and restores focus after %s',async action=>{
 const confirm=vi.fn()
 await act(async()=>root.render(<MemoryRouter><MoreReaderActions><RegenerateAction onConfirm={confirm}/></MoreReaderActions></MemoryRouter>))
 const menu=node.querySelector('button')!
 act(()=>menu.click())
 act(()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Regenerate summary')!.click())
 await act(async()=>vi.dynamicImportSettled())
 const dialog=document.querySelector('[role="dialog"]')!
 expect(dialog).toBeTruthy();expect(dialog.closest('.reader-menu-panel')).toBeNull()
 expect(menu.getAttribute('aria-expanded')).toBe('false')
 act(()=>{
  if(action==='Escape')document.activeElement!.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  else [...dialog.querySelectorAll('button')].find(b=>b.textContent===action)!.click()
 })
 expect(document.querySelector('[role="dialog"]')).toBeNull()
 expect(document.activeElement).toBe(menu)
 expect(confirm).toHaveBeenCalledTimes(action==='Regenerate'?1:0)
})
it('keeps the current heading when another heading enters the observation area',()=>{
 const first=document.createElement('h2'),second=document.createElement('h2')
 first.id='first';second.id='second';node.append(first,second)
 first.getBoundingClientRect=()=>({top:100} as DOMRect)
 second.getBoundingClientRect=()=>({top:300} as DOMRect)
 const change=vi.fn(),callback=readingIntersection(change)
 const entry=(target:Element,isIntersecting=true)=>({target,isIntersecting} as IntersectionObserverEntry)
 callback([entry(first)],{} as IntersectionObserver)
 callback([entry(second)],{} as IntersectionObserver)
 expect(change).toHaveBeenLastCalledWith('first')
 callback([entry(first,false)],{} as IntersectionObserver)
 expect(change).toHaveBeenLastCalledWith('second')
 second.remove();callback([entry(first)],{} as IntersectionObserver)
 expect(change).toHaveBeenLastCalledWith('first')
})

it('keeps a touch action mounted when the trigger blurs without a related target',async()=>{
 const action=vi.fn()
 await act(async()=>root.render(<MemoryRouter><MoreReaderActions><button onClick={action}>Download file</button></MoreReaderActions></MemoryRouter>))
 const trigger=node.querySelector('button')!
 act(()=>{trigger.focus();trigger.click()})
 act(()=>trigger.dispatchEvent(new FocusEvent('focusout',{bubbles:true,relatedTarget:null})))
 const item=[...node.querySelectorAll('button')].find(b=>b.textContent==='Download file')!
 expect(item).toBeTruthy()
 act(()=>item.click())
 expect(action).toHaveBeenCalledOnce()
 expect(trigger.getAttribute('aria-expanded')).toBe('false')
})

it('still closes when focus actually moves outside or an outside pointer is pressed',async()=>{
 await act(async()=>root.render(<MemoryRouter><MoreReaderActions><button>Download file</button></MoreReaderActions><button id="outside">Outside</button></MemoryRouter>))
 const trigger=node.querySelector('button')!,outside=node.querySelector('#outside')!
 act(()=>{trigger.focus();trigger.click()})
 act(()=>trigger.dispatchEvent(new FocusEvent('focusout',{bubbles:true,relatedTarget:outside})))
 expect(trigger.getAttribute('aria-expanded')).toBe('false')
 act(()=>trigger.click())
 act(()=>outside.dispatchEvent(new Event('pointerdown',{bubbles:true})))
 expect(trigger.getAttribute('aria-expanded')).toBe('false')
})
