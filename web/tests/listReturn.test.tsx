// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,expect,it,vi} from 'vitest'
import {useListReturn} from '../src/lib/listReturn'
vi.mock('../src/lib/preferences',()=>({getAccountId:()=> 'controlled'}))
let cleanup=()=>{}
afterEach(()=>{cleanup();sessionStorage.clear();vi.unstubAllGlobals()})
it('keeps the entry anchor when the surviving main scroll container resets during navigation',async()=>{
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}})
  vi.stubGlobal('CSS',{escape:(s:string)=>s})
  const main=document.createElement('main'),host=document.createElement('div')
  main.append(host);document.body.append(main)
  function List(){useListReturn('episodes:show',true);return <div data-reader-href="/viewer/entry"><a href="/viewer/entry" onClick={e=>e.preventDefault()}>Read summary</a></div>}
  const root=createRoot(host)
  cleanup=()=>{act(()=>root.unmount());main.remove()}
  await act(async()=>root.render(<List/>))
  main.scrollTop=3200
  await act(async()=>{
    main.dispatchEvent(new Event('pointerdown',{bubbles:true}))
    host.querySelector('a')!.click()
    // The next route resets the shared element before the outgoing passive
    // effect is cleaned up. Its scroll event must not overwrite the entry.
    main.scrollTop=0;main.dispatchEvent(new Event('scroll'))
  })
  cleanup();cleanup=()=>{}
  expect(JSON.parse(sessionStorage.getItem('xyz_reading:controlled:episodes:show')!)).toMatchObject({top:3200,href:'/viewer/entry'})
})
