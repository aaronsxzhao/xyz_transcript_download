// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Dashboard from '../src/pages/Dashboard'
import {clearCache} from '../src/lib/cache'
const api=vi.hoisted(()=>({fetchContentUpdates:vi.fn(),dismissContentUpdates:vi.fn(),checkPodcastsForUpdates:vi.fn(),checkVideoChannelsForUpdates:vi.fn()}))
const toast=vi.hoisted(()=>vi.fn())
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api,
 fetchStats:async()=>({podcasts:0,episodes:0,transcripts:0,summaries:0}),fetchRecentSummaries:async()=>[],fetchRecentVideoTasks:async()=>({tasks:[]})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:toast})}))
vi.mock('../src/lib/preferences',()=>({getAccountId:()=> 'owner'}))
const updates=[{item_key:'podcast:one',kind:'podcast',title:'New episode',source_title:'My show',source_id:'show',created_at:'2026-10-21'},
 {item_key:'video:two',kind:'video',title:'New video',source_title:'My channel',source_id:'video',created_at:'2026-10-21'}]
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{vi.clearAllMocks();clearCache();localStorage.clear();api.fetchContentUpdates.mockResolvedValue({items:updates});api.dismissContentUpdates.mockResolvedValue(undefined);node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache()})
async function render(){await act(async()=>root.render(<MemoryRouter><Dashboard/></MemoryRouter>))}
it('shows both podcast and video discoveries and dismisses only displayed keys',async()=>{
 await render()
 expect(node.textContent).toContain('1 episodes · 1 videos')
 expect(node.textContent).toContain('New episode')
 api.fetchContentUpdates.mockResolvedValue({items:[]})
 const close=node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement
 await act(async()=>close.click())
 expect(api.dismissContentUpdates).toHaveBeenCalledWith(['podcast:one','video:two'])
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
})
it('retains successful video discoveries when the podcast scan fails',async()=>{
 api.checkPodcastsForUpdates.mockRejectedValue(new Error('Offline'))
 api.checkVideoChannelsForUpdates.mockResolvedValue({new_videos:1,channels_checked:1})
 await render()
 const check=Array.from(node.querySelectorAll('button')).find(button=>button.textContent?.includes('Check Updates'))!
 expect(check).toBeDefined()
 await act(async()=>check.click())
 expect(api.fetchContentUpdates).toHaveBeenCalledTimes(2)
 expect(node.textContent).toContain('New video')
 expect(toast).toHaveBeenCalledWith(expect.objectContaining({title:'Some sources could not be checked'}))
})
