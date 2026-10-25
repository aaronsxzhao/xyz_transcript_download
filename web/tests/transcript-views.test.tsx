// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import TranscriptPanel from '../src/components/video/TranscriptPanel'
import TranscriptSegments from '../src/components/TranscriptSegments'

vi.mock('@tanstack/react-virtual',()=>({useVirtualizer:({count}:any)=>({getTotalSize:()=>count*64,getVirtualItems:()=>Array.from({length:count},(_,i)=>({index:i,key:i,start:i*64})),measureElement:()=>{}})}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove()})

it('makes the complete saved text accessible even when timed segments omit content',async()=>{
 const transcript={text:'Opening.\n\nThe missing middle argument and all its conditions.\n\nFinal qualification.',segments:[{start:0,end:3,text:'Opening.'}],duration:120}
 await act(async()=>root.render(<TranscriptPanel transcript={transcript}/>))
 expect(node.querySelector('[aria-label="Transcript segments"]')).not.toBeNull()
 expect(node.textContent).not.toContain('Final qualification.')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Full text')!.click())
 expect(node.querySelector('[aria-label="Full transcript text"]')?.textContent).toBe(transcript.text)
 expect(node.querySelector('[aria-pressed="true"]')?.textContent).toBe('Full text')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Timed segments')!.click())
 expect(node.querySelector('[aria-label="Transcript segments"]')?.textContent).toContain('0:00Opening.')
})

it('keeps full-text-only and segment-only transcripts readable without empty controls',async()=>{
 await act(async()=>root.render(<TranscriptSegments segments={[]} text={'Complete original text.\nFinal detail.'}/>))
 expect(node.textContent).toBe('Complete original text.\nFinal detail.')
 expect(node.querySelector('button')).toBeNull()
 await act(async()=>root.render(<TranscriptSegments segments={[{start:60,end:63,text:'Only timestamped source available.'}]}/>))
 expect(node.textContent).toContain('1:00Only timestamped source available.')
 expect(node.querySelector('button')).toBeNull()
})

it('falls back to available segments if a text-only view is followed by a segment-only source',async()=>{
 const segments=[{start:0,end:1,text:'Segment remains available.'}]
 await act(async()=>root.render(<TranscriptSegments segments={segments} text="Full source"/>))
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Full text')!.click())
 await act(async()=>root.render(<TranscriptSegments segments={segments}/>))
 expect(node.textContent).toContain('Segment remains available.')
 expect(node.textContent).not.toContain('No transcript available')
})
