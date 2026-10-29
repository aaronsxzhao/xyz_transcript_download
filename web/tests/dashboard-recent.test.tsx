// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import DashboardRecent from '../src/components/DashboardRecent'
import Dashboard from '../src/pages/Dashboard'
import {fetchLibrary,fetchStats,fetchContentUpdates,processEpisode,checkPodcastsForUpdates,checkVideoChannelsForUpdates,type LibraryItem} from '../src/lib/api'
import {clearCache,getCache,setCache,invalidateForMutation} from '../src/lib/cache'
import {useStore} from '../src/lib/store'
vi.mock('../src/lib/api',async load=>({...await load<object>(),fetchLibrary:vi.fn(),fetchStats:vi.fn(),fetchContentUpdates:vi.fn(),processEpisode:vi.fn(),checkPodcastsForUpdates:vi.fn(),checkVideoChannelsForUpdates:vi.fn()}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
const toast=vi.hoisted(()=>vi.fn())
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:toast})}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
const item=(id:string,kind:'podcast'|'video'='video',article=false):LibraryItem=>({id,kind,content_type:article?'article':kind==='podcast'?'audio':'video',title:'Saved '+id,source:'Source',date:'2026-10-27T03:00:00Z',status:'completed'})
const button=(name:string)=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()===name)!
const titles=()=>[...node.querySelectorAll('.publication-feature h2, .dashboard-recent-notes h3')].map(el=>el.textContent)
async function mount(dashboard=false){await act(async()=>root.render(<MemoryRouter>{dashboard?<Dashboard/>:<DashboardRecent revision={0}/>}</MemoryRouter>))}
beforeEach(()=>{
 document.documentElement.dataset.design='classic';document.documentElement.dataset.theme='dark'
 vi.resetAllMocks();localStorage.clear();sessionStorage.clear();clearCache();useStore.getState().reset()
 localStorage.setItem('xyz_user',JSON.stringify({id:'owner',authenticated:true}))
 vi.mocked(fetchLibrary).mockResolvedValue({items:[],next_cursor:null})
 vi.mocked(fetchStats).mockResolvedValue({} as any);vi.mocked(fetchContentUpdates).mockResolvedValue({items:[]})
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache();useStore.getState().reset();vi.useRealTimers();vi.restoreAllMocks()})
it('shows a unified twelve-item page and pages without losing or duplicating records',async()=>{
 const rows=Array.from({length:12},(_,i)=>item(String(i),i===0?'podcast':'video',i===1))
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:rows,next_cursor:'next'})
 await mount()
 expect(titles()).toEqual(rows.map(r=>r.title))
 expect(node.querySelectorAll('.publication-feature')).toHaveLength(0)
 expect(node.querySelectorAll('.dashboard-recent-notes h3')).toHaveLength(12)
 expect(new URLSearchParams(vi.mocked(fetchLibrary).mock.calls[0][0]).get('limit')).toBe('12')
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[rows[11],item('0'),item('older'),item('oldest')],next_cursor:null})
 await act(async()=>button('Load more').click())
 expect(titles()).toHaveLength(15)
 expect(fetchLibrary).toHaveBeenLastCalledWith(expect.any(String),'next',expect.any(AbortSignal))
 expect(node.textContent).toContain('15 loaded')
 expect([...node.querySelectorAll('button')].some(b=>b.textContent==='Load more')).toBe(false)
})
it('queries article membership on the server and labels original text as an article',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('video')],next_cursor:null})
 await mount()
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('older-article','video',true)],next_cursor:null})
 await act(async()=>button('Articles').click())
 const params=new URLSearchParams(vi.mocked(fetchLibrary).mock.calls.at(-1)![0])
 expect(params.get('kind')).toBe('article');expect(params.get('sort')).toBe('newest')
 expect(titles()).toEqual(['Saved older-article'])
 expect(node.textContent).toContain('Read article');expect(node.querySelector('time')?.textContent).toContain('Saved')
 expect(node.querySelector('.reading-history-card')?.getAttribute('href')).toBe('/videos/older-article')
})
it('aborts an older filter read and prevents its late response from overwriting or caching',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(fetchLibrary).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount()
 const signal=vi.mocked(fetchLibrary).mock.calls[0][2]!
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('article','video',true)],next_cursor:null})
 await act(async()=>button('Articles').click())
 expect(signal.aborted).toBe(true)
 await act(async()=>finish({items:[item('stale')],next_cursor:null}))
 expect(titles()).toEqual(['Saved article']);expect(getCache('library_page:dashboard_recent:v1:')).toBeNull()
})
it('retains the loaded page when loading more fails and retries that cursor',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('existing')],next_cursor:'next'})
 await mount()
 vi.mocked(fetchLibrary).mockRejectedValueOnce(new Error('Page read failed'))
 await act(async()=>button('Load more').click())
 expect(titles()).toEqual(['Saved existing']);expect(node.querySelector('[role=alert]')).not.toBeNull()
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('new')],next_cursor:null})
 await act(async()=>button('Retry').click())
 expect(fetchLibrary).toHaveBeenLastCalledWith(expect.any(String),'next',expect.any(AbortSignal))
 expect(titles()).toEqual(['Saved existing','Saved new'])
})
it('keeps a cached page visible during refresh and distinguishes failures from empty content',async()=>{
 setCache('library_page:dashboard_recent:v1:',{items:[item('cached')],next_cursor:null})
 vi.mocked(fetchLibrary).mockRejectedValueOnce(new Error('Page read failed'))
 await mount()
 expect(titles()).toEqual(['Saved cached']);expect(node.textContent).not.toContain('No saved content yet')
 expect(node.querySelector('[role=alert]')).not.toBeNull()
})
it('refreshes recent content for a fast completion that never emitted an active state',async()=>{
 vi.useFakeTimers();await mount(true)
 expect(fetchLibrary).toHaveBeenCalledOnce()
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[item('completed-fast')],next_cursor:null})
 await act(async()=>useStore.getState().updateVideoTask({id:'fast',status:'success',title:'Completed',updated_at:'2026-10-27T03:00:00Z'} as any))
 await act(async()=>vi.advanceTimersByTimeAsync(300))
 expect(titles()).toEqual(['Saved completed-fast']);expect(fetchLibrary).toHaveBeenCalledTimes(2)
})
it('does not insert a podcast submission into another account after its acknowledgement arrives',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(processEpisode).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount(true)
 const input=node.querySelector<HTMLInputElement>('#dashboard-add-content input')!
 await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'https://www.xiaoyuzhoufm.com/episode/one');input.dispatchEvent(new Event('input',{bubbles:true}))})
 await act(async()=>input.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})))
 localStorage.setItem('xyz_user',JSON.stringify({id:'another',authenticated:true}))
 await act(async()=>finish({job_id:'private',episode_id:'one'}))
 expect(useStore.getState().jobs).toEqual([]);expect(toast).not.toHaveBeenCalled()
})
it('prevents two checks submitted within the same render from scanning sources twice',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(checkPodcastsForUpdates).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 vi.mocked(checkVideoChannelsForUpdates).mockResolvedValue({new_videos:0} as any)
 await mount(true)
 const check=node.querySelector<HTMLButtonElement>('[aria-label="Check Updates"]')!
 await act(async()=>{check.click();check.click()})
 expect(checkPodcastsForUpdates).toHaveBeenCalledOnce();expect(checkVideoChannelsForUpdates).toHaveBeenCalledOnce()
 await act(async()=>finish({new_episodes:0}))
})
it('keeps unreadable failed rows out of the saved-content feed',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[{...item('failed'),status:'failed'},item('ready')],next_cursor:null})
 await mount()
 expect(titles()).toEqual(['Saved ready'])
})
it('does not let an old dashboard instance overwrite newer notification cache after unmount',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(fetchContentUpdates).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount(true)
 act(()=>root.unmount());root=createRoot(node)
 const fresh={item_key:'video:new',kind:'video' as const,title:'Actual new content',source_title:'Source',source_id:'new',created_at:'2026-10-27T04:00:00Z'}
 vi.mocked(fetchContentUpdates).mockResolvedValueOnce({items:[fresh]})
 await mount(true)
 await act(async()=>finish({items:[{...fresh,item_key:'video:old',title:'Stale item'}]}))
 expect((getCache<any>('content-updates:v2')).items[0].title).toBe('Actual new content')
})

it.each(['/api/video-notes/tasks/removed','/api/episodes/removed'])('invalidates recent saved-content cache after %s changes',async url=>{
 setCache('library_page:dashboard_recent:v1:',{items:[item('removed')],next_cursor:null})
 invalidateForMutation(url)
 let finish!:(value:any)=>void
 vi.mocked(fetchLibrary).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount()
 expect(titles()).toEqual([])
 await act(async()=>finish({items:[],next_cursor:null}))
 expect(node.textContent).toContain('No saved content yet')
})

it('switches the saved feed to the editorial feature without losing records or changing the filter',async()=>{
 const rows=[item('podcast','podcast'),item('video')]
 vi.mocked(fetchLibrary).mockResolvedValue({items:rows,next_cursor:null})
 await mount()
 await act(async()=>{const {setAppearance}=await import('../src/lib/theme');await setAppearance('editorial','light')})
 expect(titles()).toEqual(rows.map(r=>r.title))
 expect(node.querySelectorAll('.publication-feature')).toHaveLength(1)
 expect(node.querySelector('.publication-feature')?.getAttribute('href')).toBe('/viewer/podcast')
 await act(async()=>{const {setAppearance}=await import('../src/lib/theme');await setAppearance('classic','dark')})
 expect(node.querySelectorAll('.publication-feature')).toHaveLength(0)
 expect(titles()).toEqual(rows.map(r=>r.title))
})
