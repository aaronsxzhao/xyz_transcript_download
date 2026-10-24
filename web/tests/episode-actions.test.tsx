// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Episodes from '../src/pages/Episodes'
import {fetchPodcast,fetchPodcasts,fetchEpisodes,fetchEpisode,processEpisode,deleteEpisode,ApiError,type Episode,type Podcast} from '../src/lib/api'
import {CacheKeys,setCache,getCache,clearCache} from '../src/lib/cache'
import {useStore} from '../src/lib/store'
vi.mock('../src/lib/api',async load=>({...await load<object>(),fetchPodcast:vi.fn(),fetchPodcasts:vi.fn(),fetchEpisodes:vi.fn(),fetchEpisode:vi.fn(),processEpisode:vi.fn(),deleteEpisode:vi.fn()}))
const notify=vi.hoisted(()=>vi.fn())
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:notify})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/lib/seen',()=>({markSeen:()=>{},isNewItem:()=>false}))
vi.mock('../src/lib/summaryPrefetch',()=>({prefetchSummary:()=>{}}))
const show=(platform='apple'):Podcast=>({pid:'show',title:'Saved source',platform,author:'Author',description:'',cover_url:'',feed_url:'',episode_count:2,summarized_count:0})
const episode=(eid:string):Episode=>({eid,pid:'show',title:'Episode '+eid,description:'',duration:60,pub_date:'',created_at:'',audio_url:'',cover_url:'',status:'pending',has_summary:false,has_transcript:false,topics_count:0,key_points_count:0})
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.resetAllMocks();useStore.getState().reset();localStorage.clear();sessionStorage.clear();clearCache();vi.stubGlobal('confirm',()=>true)
 vi.mocked(fetchPodcast).mockResolvedValue(show());vi.mocked(fetchPodcasts).mockResolvedValue([]);vi.mocked(fetchEpisodes).mockResolvedValue([episode('one'),episode('two')])
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache();useStore.getState().reset();vi.unstubAllGlobals();vi.restoreAllMocks()})
async function mount(){await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts/show/episodes']}><Routes><Route path='/podcasts/:pid/episodes' element={<Episodes/>}/></Routes></MemoryRouter>))}
const card=(id:string)=>[...node.querySelectorAll('h3')].find(el=>el.textContent==='Episode '+id)!.closest('.rounded-xl')!
const process=(id:string)=>[...card(id).querySelectorAll('button')].find(el=>el.textContent?.trim()==='Process')!
it.each(['apple','spotify','local'])('loads source details on a cold %s page without blocking its episodes',async platform=>{
 let finish!:(value:Podcast)=>void
 vi.mocked(fetchPodcast).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount()
 expect(node.textContent).toContain('Episode one');expect(process('one').disabled).toBe(true)
 await act(async()=>finish(show(platform)))
 expect(node.querySelector('h1')?.textContent).toBe('Saved source')
 vi.mocked(processEpisode).mockResolvedValueOnce({job_id:'queued'})
 await act(async()=>process('one').click())
 expect(processEpisode).toHaveBeenCalledWith((platform==='spotify'?'apple':platform)+'://one')
 expect(fetchPodcasts).not.toHaveBeenCalled()
})
it('can retry failed source details while keeping the loaded episode list',async()=>{
 vi.mocked(fetchPodcast).mockRejectedValueOnce(new ApiError('Source details unavailable',503)).mockResolvedValueOnce(show())
 await mount()
 expect(node.textContent).toContain('Episode one');expect(process('one').disabled).toBe(true)
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Source details unavailable')
 await act(async()=>node.querySelector<HTMLButtonElement>('[role=alert] button')!.click())
 expect(process('one').disabled).toBe(false);expect(fetchEpisodes).toHaveBeenCalledOnce()
})
it('retains a separate pending state for each concurrent episode submission',async()=>{
 let first!:(value:any)=>void,second!:(value:any)=>void
 vi.mocked(processEpisode).mockImplementationOnce(()=>new Promise(resolve=>{first=resolve})).mockImplementationOnce(()=>new Promise(resolve=>{second=resolve}))
 await mount();await act(async()=>process('one').click());await act(async()=>process('two').click())
 expect(process('one').disabled).toBe(true);expect(process('two').disabled).toBe(true)
 expect(card('one').querySelector<HTMLButtonElement>('[title="Delete episode"]')!.disabled).toBe(true)
 await act(async()=>first({job_id:'first'}))
 expect(process('two').disabled).toBe(true)
 await act(async()=>second({job_id:'second'}))
 expect(useStore.getState().jobs).toHaveLength(2)
})
it('preserves the actual submission failure reason',async()=>{
 vi.mocked(processEpisode).mockRejectedValueOnce(new Error('No confirmation received. Check Processing before submitting again.'))
 await mount();await act(async()=>process('one').click())
 expect(notify).toHaveBeenCalledWith(expect.objectContaining({type:'error',message:expect.stringContaining('No confirmation received')}))
})
it('does not resurrect a confirmed deletion when an older episode snapshot arrives',async()=>{
 const now=Date.now();const clock=vi.spyOn(Date,'now').mockReturnValue(now-61000)
 setCache(CacheKeys.PODCAST('show'),show());setCache(CacheKeys.EPISODES('show'),[episode('one'),episode('two')]);clock.mockReturnValue(now)
 let finish!:(value:Episode[])=>void
 vi.mocked(fetchEpisodes).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(deleteEpisode).mockResolvedValueOnce({message:'Deleted'})
 await mount();await act(async()=>card('one').querySelector<HTMLButtonElement>('[title="Delete episode"]')!.click())
 await act(async()=>finish([episode('one'),episode('two')]))
 expect(node.textContent).not.toContain('Episode one');expect(node.textContent).toContain('Episode two')
 expect(getCache<Episode[]>(CacheKeys.EPISODES('show'))?.map(row=>row.eid)).toEqual(['two'])
})
it('persists completed episode annotations so revisiting the page keeps its summary link',async()=>{
 await mount()
 vi.mocked(fetchEpisode).mockResolvedValueOnce({...episode('one'),has_transcript:true,has_summary:true,topics_count:4,key_points_count:8})
 await act(async()=>useStore.getState().updateJob({job_id:'done',episode_id:'one',status:'completed',progress:100,message:'Complete'}))
 expect(card('one').textContent).toContain('View')
 expect(getCache<Episode[]>(CacheKeys.EPISODES('show'))?.find(row=>row.eid==='one')?.has_summary).toBe(true)
})
it('keeps pagination available after deleting a row while source counts are stale',async()=>{
 vi.mocked(fetchEpisodes).mockResolvedValueOnce(Array.from({length:50},(_,i)=>episode(String(i))))
 vi.mocked(deleteEpisode).mockResolvedValueOnce({message:'Deleted'})
 await mount()
 expect(node.textContent).toContain('Load more episodes')
 await act(async()=>card('0').querySelector<HTMLButtonElement>('[title="Delete episode"]')!.click())
 expect(node.textContent).toContain('Load more episodes')
})
it('keeps a full cached page pageable even when source counts are older',async()=>{
 setCache(CacheKeys.PODCAST('show'),show());setCache(CacheKeys.EPISODES('show'),Array.from({length:50},(_,i)=>episode(String(i))))
 await mount()
 expect(node.textContent).toContain('Load more episodes')
 expect(fetchEpisodes).not.toHaveBeenCalled()
})
