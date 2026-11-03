// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {it,expect,vi} from 'vitest'
import ItemActions from '../src/components/ItemActions'
import {cancelPrefetch} from '../src/lib/summaryPrefetch'
vi.mock('../src/lib/summaryPrefetch',()=>({cancelPrefetch:vi.fn()}))
it('keeps destructive menu interactions from scheduling a row summary prefetch',()=>{
 const rowTouch=vi.fn(),node=document.createElement('div'),root=createRoot(node)
 document.body.append(node)
 try {
  act(()=>root.render(<div onTouchStart={rowTouch}><ItemActions title="Saved episode" kind="episode" busy={false} hasSummary onDeleteItem={()=>{}} onDeleteSummary={()=>{}}/></div>))
  const summary=node.querySelector('summary')!
  act(()=>summary.dispatchEvent(new Event('touchstart',{bubbles:true})))
  expect(rowTouch).not.toHaveBeenCalled()
  expect(cancelPrefetch).toHaveBeenCalledOnce()
  act(()=>summary.focus())
  expect(cancelPrefetch).toHaveBeenCalledTimes(2)
  act(()=>summary.dispatchEvent(new MouseEvent('pointerover',{bubbles:true})))
  expect(cancelPrefetch).toHaveBeenCalledTimes(3)
 } finally {act(()=>root.unmount());node.remove()}
})
