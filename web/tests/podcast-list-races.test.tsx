// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route,Link} from 'react-router-dom'
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

it('keeps each subscription busy until its own refresh completes',async()=>{
 setCache(CacheKeys.PODCASTS,[row('one'),row('two')])
 vi.mocked(fetchPodcasts).mockResolvedValue([row('one'),row('two')])
 let first!:(value:any)=>void,second!:(value:any)=>void
 vi.mocked(refreshPodcast).mockImplementationOnce(()=>new Promise(resolve=>{first=resolve})).mockImplementationOnce(()=>new Promise(resolve=>{second=resolve}))
 await mount()
 const refresh=[...node.querySelectorAll<HTMLButtonElement>('[title="Refresh episodes"]')]
 const remove=[...node.querySelectorAll<HTMLButtonElement>('[title="Remove podcast"]')]
 await act(async()=>refresh[0].click())
 await act(async()=>refresh[1].click())
 expect(refresh.map(button=>button.disabled)).toEqual([true,true])
 expect(remove.map(button=>button.disabled)).toEqual([true,true])
 await act(async()=>first({message:'Updated',total:1}))
 expect(refresh.map(button=>button.disabled)).toEqual([false,true])
 await act(async()=>second({message:'Updated',total:1}))
 expect(refresh.map(button=>button.disabled)).toEqual([false,false])
})

it('does not duplicate refresh requests before React renders or during a bulk check',async()=>{
 setCache(CacheKeys.PODCASTS,[row('one')]);vi.mocked(fetchPodcasts).mockResolvedValue([row('one')])
 let finish!:(value:any)=>void
 vi.mocked(refreshPodcast).mockImplementation(()=>new Promise(resolve=>{finish=resolve}))
 await mount()
 const refresh=node.querySelector<HTMLButtonElement>('[title="Refresh episodes"]')!
 const bulk=[...node.querySelectorAll('button')].find(button=>button.textContent?.includes('Check Updates'))!
 await act(async()=>{refresh.click();refresh.click();bulk.click()})
 expect(refreshPodcast).toHaveBeenCalledTimes(1)
 await act(async()=>finish({message:'Updated',total:1}))
 await act(async()=>{bulk.click();bulk.click();refresh.click()})
 expect(refreshPodcast).toHaveBeenCalledTimes(2)
 expect(refresh.disabled).toBe(true)
 expect(node.querySelector<HTMLButtonElement>('[title="Remove podcast"]')!.disabled).toBe(true)
 await act(async()=>finish({message:'Updated',total:1}))
})

it('keeps concurrent deletions independent and restores a failed row for retry',async()=>{
 setCache(CacheKeys.PODCASTS,[row('one'),row('two')]);vi.mocked(fetchPodcasts).mockResolvedValue([row('one'),row('two')])
 let first!:()=>void,fail!:(error:Error)=>void
 vi.mocked(removePodcast).mockImplementationOnce(()=>new Promise(resolve=>{first=resolve})).mockImplementationOnce(()=>new Promise((_,reject)=>{fail=reject}))
 await mount()
 const remove=[...node.querySelectorAll<HTMLButtonElement>('[title="Remove podcast"]')]
 await act(async()=>{remove[0].click();remove[0].click()})
 await act(async()=>remove[1].click())
 expect(removePodcast).toHaveBeenCalledTimes(2)
 expect(remove.map(button=>button.disabled)).toEqual([true,true])
 await act(async()=>first())
 expect(remove[1].disabled).toBe(true)
 await act(async()=>fail(new Error('Unavailable')))
 expect(node.textContent).toContain('Show two')
 expect(remove[1].disabled).toBe(false)
})


it('does not navigate away from the new page when a Spotify import finishes in the background',async()=>{
 vi.mocked(fetchPodcasts).mockResolvedValue([])
 let finish!:(value:Podcast)=>void
 vi.mocked(addPodcast).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts']}><Link to="/library">Go to Library</Link><Routes><Route path="/podcasts" element={<Podcasts/>}/><Route path="/library" element={<h1>Library destination</h1>}/><Route path="/podcasts/:pid/episodes" element={<h1>Unexpected redirect</h1>}/></Routes></MemoryRouter>))
 await act(async()=>[...node.querySelectorAll('button')].find(button=>button.textContent?.trim()==='Add Podcast')!.click())
 const input=node.querySelector<HTMLInputElement>('form input')!
 await act(async()=>{
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'https://open.spotify.com/episode/123')
  input.dispatchEvent(new Event('input',{bubbles:true}))
 })
 await act(async()=>input.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))
 await act(async()=>node.querySelector<HTMLAnchorElement>('a')!.click())
 expect(node.textContent).toContain('Library destination')
 await act(async()=>finish({...row('new'),resolved_episode_id:'episode'}))
 expect(node.textContent).toContain('Library destination')
})
