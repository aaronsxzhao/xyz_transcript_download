// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,useNavigate} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Videos from '../src/pages/Videos'
import Podcasts from '../src/pages/Podcasts'
import {clearCache} from '../src/lib/cache'
import {useStore} from '../src/lib/store'
const api=vi.hoisted(()=>({fetchVideoChannels:vi.fn(),fetchVideoTasksByChannel:vi.fn(),checkVideoChannelsForUpdates:vi.fn(),fetchPodcasts:vi.fn(),refreshPodcast:vi.fn(),notify:vi.fn()}))
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:api.notify,removeToast:vi.fn()})}))
vi.mock('../src/components/CachedImage',()=>({default:()=>null}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{}}))
vi.mock('../src/lib/seen',()=>({markSeen:()=>{},isNewItem:()=>false}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.resetAllMocks();localStorage.clear();sessionStorage.clear();clearCache();useStore.getState().reset()
 api.fetchVideoChannels.mockResolvedValue({channels:[]});api.fetchVideoTasksByChannel.mockResolvedValue({tasks:[],next_cursor:null})
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache();useStore.getState().reset()})
it.each(['twitter','substack'])('offers %s source checks with the platform and channel scope and truthful failure details',async platform=>{
 api.checkVideoChannelsForUpdates.mockResolvedValue({new_videos:0,channels_checked:0,channels_failed:1,failures:[{channel:'Writer',platform,message:'Public source is restricted'}]})
 await act(async()=>root.render(<MemoryRouter initialEntries={[`/videos?platform=${platform}&channel=Writer`]}><Videos/></MemoryRouter>))
 const button=node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!
 expect(button).not.toBeNull();expect(button.textContent).toContain('Check Updates')
 await act(async()=>button.click())
 await act(async()=>{await vi.dynamicImportSettled()})
 expect(api.checkVideoChannelsForUpdates).toHaveBeenCalledWith({channel:'Writer',platform},expect.any(Function))
 expect(node.textContent).toContain('Public source is restricted')
 expect(api.notify).toHaveBeenCalledOnce()
 expect(api.notify).toHaveBeenCalledWith(expect.objectContaining({title:'Update check incomplete'}))
})
it('reports partial discovery once instead of stacking success and failure notifications',async()=>{
 api.checkVideoChannelsForUpdates.mockResolvedValue({new_videos:2,channels_checked:1,channels_failed:1,failures:[{channel:'Unavailable',platform:'twitter',message:'Restricted'}]})
 await act(async()=>root.render(<MemoryRouter initialEntries={['/videos?platform=twitter']}><Videos/></MemoryRouter>))
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!.click())
 expect(api.notify).toHaveBeenCalledOnce()
 expect(api.notify).toHaveBeenCalledWith(expect.objectContaining({title:'New items found · check incomplete'}))
})
it('shows the Spotify update action and never reports a failed RSS refresh as no new episodes',async()=>{
 api.fetchPodcasts.mockResolvedValue([{pid:'show',platform:'spotify',title:'Spotify show',episode_count:2,summarized_count:0}])
 api.refreshPodcast.mockRejectedValue(new Error('Public RSS feed unavailable'))
 await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts?platform=spotify']}><Podcasts/></MemoryRouter>))
 const button=node.querySelector<HTMLButtonElement>('[aria-label="Check podcast updates"]')!
 expect(button.textContent).toContain('Check Updates')
 expect(button.querySelector('span')?.className).not.toContain('hidden')
 await act(async()=>button.click())
 await act(async()=>{await vi.dynamicImportSettled()})
 expect(api.refreshPodcast).toHaveBeenCalledWith('show')
 expect(api.notify).toHaveBeenCalledWith(expect.objectContaining({title:'Update check incomplete',message:expect.stringContaining('Public RSS feed unavailable')}))
})

it('does not show a late failed scan under a different platform after navigation',async()=>{
 let finish!:(result:any)=>void
 api.checkVideoChannelsForUpdates.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 function Switch(){const navigate=useNavigate();return <button onClick={()=>navigate('/videos?platform=substack')}>Switch source</button>}
 await act(async()=>root.render(<MemoryRouter initialEntries={['/videos?platform=twitter']}><Switch/><Videos/></MemoryRouter>))
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!.click())
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Switch source')!.click())
 await act(async()=>finish({new_videos:0,channels_checked:0,channels_failed:1,failures:[{channel:'Old X source',platform:'twitter',message:'Old timeline restricted'}]}))
 expect(node.textContent).not.toContain('Old timeline restricted')
})

it('shows completed source progress and preserves an interrupted report without a false all-caught-up toast',async()=>{
 let finish!:(result:any)=>void
 api.checkVideoChannelsForUpdates.mockImplementationOnce((_opts,progress)=>{
  progress({new_videos:2,channels_checked:1,channels_processed:1,channels_total:3})
  return new Promise(resolve=>{finish=resolve})
 })
 await act(async()=>root.render(<MemoryRouter initialEntries={['/videos?platform=twitter']}><Videos/></MemoryRouter>))
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!.click())
 await act(async()=>{await vi.dynamicImportSettled()})
 expect(node.textContent).toContain('Checked 1 / 3 sources · 2 new items saved')
 expect(node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!.disabled).toBe(true)
 await act(async()=>finish({new_videos:2,channels_checked:1,channels_failed:0,interrupted:'Remaining sources were not checked'}))
 expect(node.textContent).toContain('Remaining sources were not checked')
 expect(api.notify).toHaveBeenCalledOnce()
 expect(api.notify).toHaveBeenCalledWith(expect.objectContaining({title:'New items found · check incomplete'}))
})

it('keeps live task progress visible while a channel refresh is waiting, and rejects its stale response',async()=>{
 const pending={id:'live',title:'Live source',url:'https://x.com/i/status/1',platform:'twitter',channel:'Writer',status:'pending',progress:0,message:'Queued',created_at:'2026-10-26',updated_at:'2026-10-26T10:00:00Z'} as any
 api.fetchVideoTasksByChannel.mockResolvedValue({tasks:[pending],next_cursor:null})
 api.checkVideoChannelsForUpdates.mockResolvedValue({new_videos:1,channels_checked:1})
 await act(async()=>root.render(<MemoryRouter initialEntries={['/videos?platform=twitter&channel=Writer']}><Videos/></MemoryRouter>))
 expect(node.querySelector('.video-task-list')?.textContent).toContain('Queued')
 let finish!:(value:any)=>void
 api.fetchVideoTasksByChannel.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await act(async()=>node.querySelector<HTMLButtonElement>('[aria-label="Check source updates"]')!.click())
 await act(async()=>useStore.getState().updateVideoTask({...pending,status:'summarizing',progress:78,message:'Writing',updated_at:'2026-10-26T10:00:05Z'}))
 expect(node.querySelector('.video-task-list')?.textContent).toContain('Generating summary')
 await act(async()=>finish({tasks:[pending],next_cursor:null}))
 expect(node.querySelector('.video-task-list')?.textContent).toContain('Generating summary')
})
