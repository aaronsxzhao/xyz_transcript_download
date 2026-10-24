// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Podcasts from '../src/pages/Podcasts'
import {CacheKeys,setCache,getCache,clearCache} from '../src/lib/cache'
import {fetchPodcasts,removePodcast,addPodcast,refreshPodcast,type Podcast} from '../src/lib/api'
vi.mock('../src/lib/api',async load=>({...await load<object>(),fetchPodcasts:vi.fn(),removePodcast:vi.fn(),addPodcast:vi.fn(),refreshPodcast:vi.fn()}))
const notify=vi.hoisted(()=>vi.fn())
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:notify,removeToast:vi.fn()})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
const row=(pid:string):Podcast=>({pid,title:'Show '+pid,author:'Author',description:'',cover_url:'',episode_count:1,summarized_count:0,platform:'apple',feed_url:''})
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();sessionStorage.clear();clearCache();vi.stubGlobal('confirm',()=>true);node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache();vi.unstubAllGlobals()})
async function mount(){await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts?platform=apple']}><Podcasts/></MemoryRouter>))}
it('does not resurrect a removed podcast when the preceding list request arrives late',async()=>{
 let finish!:(rows:Podcast[])=>void
 setCache(CacheKeys.PODCASTS,[row('one'),row('two')])
 vi.mocked(fetchPodcasts).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(removePodcast).mockResolvedValueOnce(undefined)
 await mount()
 await act(async()=>node.querySelector<HTMLButtonElement>('[title="Remove podcast"]')!.click())
 expect(node.textContent).not.toContain('Show one')
 await act(async()=>finish([row('one'),row('two')]))
 expect(node.textContent).not.toContain('Show one')
 expect(node.textContent).toContain('Show two')
 expect(getCache<Podcast[]>(CacheKeys.PODCASTS)?.map(row=>row.pid)).toEqual(['two'])
})
it('retains a newly added subscription when an older list snapshot arrives',async()=>{
 let finish!:(rows:Podcast[])=>void
 setCache(CacheKeys.PODCASTS,[row('one')])
 vi.mocked(fetchPodcasts).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(addPodcast).mockResolvedValueOnce(row('new'))
 await mount()
 await act(async()=>[...node.querySelectorAll('button')].find(button=>button.textContent?.trim()==='Add Podcast')!.click())
 const input=node.querySelector<HTMLInputElement>('form input')!
 await act(async()=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'https://podcasts.apple.com/podcast/id123')
  input.dispatchEvent(new Event('input',{bubbles:true}))
 })
 await act(async()=>input.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))
 await act(async()=>finish([row('one')]))
 expect(node.textContent).toContain('Show new')
 expect(getCache<Podcast[]>(CacheKeys.PODCASTS)?.map(row=>row.pid)).toEqual(['new','one'])
})
it('ignores a superseded read failure after a refresh has loaded fresh results',async()=>{
 let fail!:(error:Error)=>void
 setCache(CacheKeys.PODCASTS,[row('one')])
 vi.mocked(fetchPodcasts).mockImplementationOnce(()=>new Promise((_,reject)=>{fail=reject})).mockResolvedValueOnce([row('one'),row('new')])
 vi.mocked(refreshPodcast).mockResolvedValueOnce({message:'Updated',total:2})
 await mount()
 await act(async()=>node.querySelector<HTMLButtonElement>('[title="Refresh episodes"]')!.click())
 await act(async()=>fail(new Error('Old request disconnected')))
 expect(node.textContent).toContain('Show new')
 expect(node.textContent).not.toContain('Cannot load your podcasts')
})
it('retains the subscription and accepts fresh data when removal fails',async()=>{
 let finish!:(rows:Podcast[])=>void
 setCache(CacheKeys.PODCASTS,[row('one')])
 vi.mocked(fetchPodcasts).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(removePodcast).mockRejectedValueOnce(new Error('Disconnected'))
 await mount()
 await act(async()=>node.querySelector<HTMLButtonElement>('[title="Remove podcast"]')!.click())
 expect(node.textContent).toContain('Show one')
 expect(notify).toHaveBeenCalledWith(expect.objectContaining({type:'error',message:'Disconnected'}))
 await act(async()=>finish([row('one'),row('new')]))
 expect(node.textContent).toContain('Show new')
 expect(getCache<Podcast[]>(CacheKeys.PODCASTS)?.map(row=>row.pid)).toEqual(['one','new'])
})
