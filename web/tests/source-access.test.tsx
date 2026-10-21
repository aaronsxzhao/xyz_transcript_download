// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {it,expect} from 'vitest'
import SourceAccessNotice from '../src/components/SourceAccessNotice'
it('explains purchase restrictions and links to the original without displaying a normal summary',()=>{
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 act(()=>root.render(<SourceAccessNotice status="purchase_required" message="Purchase required on Xiaoyuzhou." episodeId="6ad08b370e4e410a05bd4fd0" warning="This summary is based on an incomplete transcript."/>))
 expect(node.querySelector('[role="alert"]')?.textContent).toContain('Purchase required')
 expect(node.textContent).toContain('incomplete transcript')
 expect(node.querySelector('a')?.href).toBe('https://www.xiaoyuzhoufm.com/episode/6ad08b370e4e410a05bd4fd0')
 act(()=>root.unmount());node.remove()
})
it('does not falsely label unverified or playable sources as paid',()=>{
 const node=document.createElement('div');const root=createRoot(node)
 act(()=>root.render(<SourceAccessNotice status="unknown"/>));expect(node.textContent).toBe('')
 act(()=>root.render(<SourceAccessNotice status="available"/>));expect(node.textContent).toBe('')
 act(()=>root.unmount())
})
