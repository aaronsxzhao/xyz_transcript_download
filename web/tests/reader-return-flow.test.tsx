// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,useLocation,useNavigate} from 'react-router-dom'
import {it,expect} from 'vitest'
import {useTrackReaderOrigin,useReaderReturn} from '../src/lib/readerReturn'
;(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true
function Harness(){useTrackReaderOrigin();const loc=useLocation(),go=useNavigate(),back=useReaderReturn();return <><output>{loc.pathname+loc.search}</output><button onClick={()=>go('/viewer/first')}>Open</button><button onClick={()=>go('/videos/second')}>Next</button><button onClick={back}>Back</button></>}
it('returns to the entry filters after moving between readers',async()=>{
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 await act(async()=>root.render(<MemoryRouter initialEntries={['/library?q=search&kind=podcast']}><Harness/></MemoryRouter>))
 for(const label of ['Open','Next','Back'])await act(async()=>Array.from(node.querySelectorAll('button')).find(b=>b.textContent===label)!.click())
 expect(node.querySelector('output')!.textContent).toBe('/library?q=search&kind=podcast')
 await act(async()=>root.unmount());node.remove()
})
it('direct reader entry has a predictable library fallback',async()=>{
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 await act(async()=>root.render(<MemoryRouter initialEntries={['/viewer/first']}><Harness/></MemoryRouter>))
 await act(async()=>Array.from(node.querySelectorAll('button')).find(b=>b.textContent==='Back')!.click())
 expect(node.querySelector('output')!.textContent).toBe('/library')
 await act(async()=>root.unmount());node.remove()
})
