// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Videos from '../src/pages/Videos'
import {fetchVideoChannels,fetchVideoTasksByChannel,deleteVideoTask} from '../src/lib/api'
import {useStore} from '../src/lib/store'
import {CacheKeys,clearCache,getCache,setCache} from '../src/lib/cache'

vi.mock('../src/lib/api',async original=>({...await original<object>(),fetchVideoChannels:vi.fn(),fetchVideoTasksByChannel:vi.fn(),deleteVideoTask:vi.fn()}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:vi.fn()})}))
vi.mock('../src/components/CachedImage',()=>({default:()=>null}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{}}))
vi.mock('../src/lib/seen',()=>({markSeen:()=>{},isNewItem:()=>false}))
const video={id:'deleted',title:'Example video',platform:'youtube',channel:'Example channel',url:'https://www.youtube.com/watch?v=abcdefghijk',status:'success',progress:100,created_at:'2026-10-23T08:00:00Z',updated_at:'2026-10-23T08:00:00Z'}
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{
 vi.resetAllMocks();localStorage.clear();sessionStorage.clear();clearCache();useStore.getState().reset()
 vi.mocked(fetchVideoChannels).mockResolvedValue({channels:[]} as any)
 vi.mocked(fetchVideoTasksByChannel).mockResolvedValueOnce({tasks:[video],next_cursor:'next'} as any)
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();useStore.getState().reset();clearCache()})
async function mount(){await act(async()=>root.render(<MemoryRouter initialEntries={['/videos?platform=youtube&channel=Example+channel']}><Videos/></MemoryRouter>))}
it('keeps a deleted video out of a late channel page and its saved cache',async()=>{
 let finish!:(value:any)=>void
 await mount()
 vi.mocked(fetchVideoTasksByChannel).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const more=[...node.querySelectorAll('button')].find(b=>b.textContent==='Show more videos')!
 await act(async()=>more.click())
 vi.mocked(deleteVideoTask).mockResolvedValueOnce({} as any)
 await act(async()=>node.querySelector<HTMLButtonElement>('[title="Delete video"]')!.click())
 expect(node.textContent).not.toContain('Example video')
 await act(async()=>finish({tasks:[video,{...video,id:'kept',title:'Another video'}],next_cursor:null}))
 expect(node.textContent).not.toContain('Example video')
 expect(node.textContent).toContain('Another video')
 const key=CacheKeys.CHANNEL_VIDEOS('youtube','Example channel')+':::newest'
 expect(getCache<{tasks:{id:string}[]}>(key)?.tasks.map(row=>row.id)).toEqual(['kept'])
})

it('does not restore a deleted video from a warm channel snapshot',async()=>{
 useStore.getState().removeVideoTask(video.id)
 const key=CacheKeys.CHANNEL_VIDEOS('youtube','Example channel')+':::newest'
 setCache(key,{tasks:[video,{...video,id:'kept',title:'Another video'}],next_cursor:null,at:Date.now()})
 await mount()
 expect(node.textContent).not.toContain('Example video')
 expect(node.textContent).toContain('Another video')
 expect(fetchVideoTasksByChannel).not.toHaveBeenCalled()
})

it('retains the video when the server rejects deletion',async()=>{
 await mount()
 vi.mocked(deleteVideoTask).mockRejectedValueOnce(new Error('Connection interrupted'))
 await act(async()=>node.querySelector<HTMLButtonElement>('[title="Delete video"]')!.click())
 expect(node.textContent).toContain('Example video')
 expect(useStore.getState().videoTasks.map(row=>row.id)).toContain(video.id)
})
