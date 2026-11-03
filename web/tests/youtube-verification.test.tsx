// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import YouTubeVerification from '../src/components/YouTubeVerification'
import {authFetch} from '../src/lib/api'
vi.mock('../src/lib/api',async load=>({...await load<object>(),authFetch:vi.fn()}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
const report={reference:'safe-reference',checked_at:'2026-11-03',revision:'test',cookie_present:true,metadata_ok:true,download_ok:true,sample_bytes:65536,elapsed_seconds:2,stage:'complete',code:'ok',message:'Video and sample verified.',runtime:{node:true}}
beforeEach(()=>{vi.useFakeTimers();vi.mocked(authFetch).mockReset();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers()})
async function mount(){await act(async()=>root.render(<YouTubeVerification/>))}
async function click(label:string){const button=[...node.querySelectorAll('button')].find(b=>b.textContent===label)!;await act(async()=>button.click())}
it('checks information and media separately and copies only the returned report',async()=>{
 vi.mocked(authFetch).mockResolvedValue(Response.json(report));const copy=vi.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:copy}})
 await mount();await click('Verify connection and download')
 expect(JSON.parse(String(vi.mocked(authFetch).mock.calls[0][1]?.body))).toEqual({video_url:''})
 expect(node.textContent).toContain('Video information: passed');expect(node.textContent).toContain('Media sample: passed (65536 bytes)')
 await click('Copy diagnostic report');expect(JSON.parse(copy.mock.calls[0][0])).toEqual(report)
})
it('does not label metadata-only access as a successful media download',async()=>{
 vi.mocked(authFetch).mockResolvedValue(Response.json({...report,download_ok:false,sample_bytes:0,code:'forbidden',message:'Media was refused.'}))
 await mount();await click('Verify connection and download');expect(node.textContent).toContain('Video information: passed');expect(node.textContent).toContain('Media sample: not verified')
})
it('keeps one request in flight and clears the report after a session change',async()=>{
 let resolve!:(r:Response)=>void;vi.mocked(authFetch).mockImplementation(()=>new Promise(r=>{resolve=r}))
 await mount();await click('Verify connection and download');expect(node.querySelector('button')!.disabled).toBe(true)
 await act(async()=>{window.dispatchEvent(new Event('xyz:session-changed'));resolve(Response.json(report))})
 expect(node.textContent).not.toContain('safe-reference');expect(node.textContent).not.toContain('passed')
})
it('times out without retrying the diagnostic POST',async()=>{
 vi.mocked(authFetch).mockImplementation(()=>new Promise(()=>{}));await mount();await click('Verify connection and download')
 await act(async()=>{await vi.advanceTimersByTimeAsync(55001)})
 expect(node.querySelector('[role="alert"]')).not.toBeNull();expect(authFetch).toHaveBeenCalledTimes(1);expect(node.querySelector('button')!.disabled).toBe(false)
})
it('clears stale success when saved cookies are changed',async()=>{
 vi.mocked(authFetch).mockResolvedValue(Response.json(report));await mount();await click('Verify connection and download')
 await act(async()=>root.render(<YouTubeVerification disabled/>));expect(node.textContent).not.toContain('safe-reference')
})
