// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Route,Routes} from 'react-router-dom'
import {expect,it,vi} from 'vitest'
import BilibiliParts from '../src/components/video/BilibiliParts'

it('distinguishes saved part navigation from unopened original sources',async()=>{
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true)
  const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
  const open=vi.spyOn(window,'open').mockImplementation(()=>null)
  await act(async()=>root.render(<MemoryRouter><Routes>
    <Route path="/" element={<BilibiliParts metadata={{bilibili_part:{page:1,cid:'1',duration:60,title:'First',url:'https://www.bilibili.com/video/BVtest?p=1'},bilibili_parts:[
      {page:1,title:'P1 First',url:'https://www.bilibili.com/video/BVtest?p=1',task_id:'one'},
      {page:2,title:'P2 Second',url:'https://www.bilibili.com/video/BVtest?p=2',task_id:'two'},
      {page:3,title:'P3 Third',url:'https://www.bilibili.com/video/BVtest?p=3'},
    ]}}/>}/>
    <Route path="/videos/two" element={<p>Second part task</p>}/>
  </Routes></MemoryRouter>))
  expect(node.textContent).toContain('Part 1 of 3')
  const select=node.querySelector('select')!
  act(()=>{select.value='3';select.dispatchEvent(new Event('change',{bubbles:true}))})
  expect(open).toHaveBeenCalledWith('https://www.bilibili.com/video/BVtest?p=3','_blank','noopener,noreferrer')
  act(()=>{select.value='2';select.dispatchEvent(new Event('change',{bubbles:true}))})
  expect(node.textContent).toContain('Second part task')
  act(()=>root.unmount());node.remove();open.mockRestore();vi.unstubAllGlobals()
})
