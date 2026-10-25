// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {detectContentPlatform} from '../src/lib/contentLinks'
import {extractNoteToc} from '../src/lib/noteMarkdown'
import PlainNote from '../src/components/PlainNote'
import Dashboard from '../src/pages/Dashboard'
const api=vi.hoisted(()=>({processEpisode:vi.fn(),generateVideoNote:vi.fn()}))
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api,fetchStats:async()=>({}),fetchRecentSummaries:async()=>[],fetchRecentVideoTasks:async()=>({tasks:[]}),fetchContentUpdates:async()=>({items:[]})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:vi.fn()})}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();sessionStorage.clear();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove()})
it.each([
 ['https://x.com/writer/status/123','twitter'],['https://twitter.com/i/web/status/123','twitter'],['https://x.com/i/article/123','twitter'],
 ['https://writer.substack.com/p/post','substack'],['https://substack.com/@writer/note/c-123','substack'],['https://publication.example/p/post','substack'],
 ['https://x.com.evil.example/writer/status/123','web'],['https://example.com/?next=https://youtube.com/watch?v=123','web'],['javascript:alert(1)',''],
 ['https://youtube.com/watch?v=abcdefghijk','youtube'],['https://b23.tv/share','bilibili']
])('detects %s by hostname', (url,platform)=>expect(detectContentPlatform(url)).toBe(platform))
it.each(['https://x.com/writer/status/123','https://writer.substack.com/p/post'])('routes %s into the existing content queue',async url=>{
 api.generateVideoNote.mockResolvedValueOnce({task_id:'social'})
 await act(async()=>root.render(<MemoryRouter><Dashboard/></MemoryRouter>))
 const input=node.querySelector<HTMLInputElement>('[aria-label="Podcast episode or video URL"]')!
 await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,url);input.dispatchEvent(new Event('input',{bubbles:true}))})
 await act(async()=>input.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))
 expect(api.generateVideoNote).toHaveBeenCalledWith(expect.objectContaining({url,platform:detectContentPlatform(url)}))
 expect(api.processEpisode).not.toHaveBeenCalled()
})
it('retains a source table of contents and original heading markers without AI cleanup',async()=>{
 const markdown='# Original\n\n## Table of Contents\n- [Detail](#detail)\n\n## Detail\n\n### 2.1 #### Literal source heading\n\nFull final paragraph.'
 await act(async()=>root.render(<PlainNote markdown={markdown} preserveSource/>))
 expect(node.textContent).toContain('Table of Contents')
 expect(node.textContent).toContain('2.1 #### Literal source heading')
 expect(node.textContent).toContain('Full final paragraph.')
 expect(extractNoteToc(markdown,true).map(item=>item.text)).toContain('Table of Contents')
})
