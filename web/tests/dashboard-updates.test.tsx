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
const before='2026-10-21T00:00:00.123456+00:00'
const updates=[{item_key:'podcast:one',kind:'podcast',title:'New episode',source_title:'My show',source_id:'show',created_at:before},
 {item_key:'video:two',kind:'video',title:'New video',source_title:'My channel',source_id:'video',created_at:before}]
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{vi.clearAllMocks();clearCache();localStorage.clear();localStorage.setItem('xyz_user',JSON.stringify({id:'owner',authenticated:true}));api.fetchContentUpdates.mockResolvedValue({items:updates,dismiss_before:before});api.dismissContentUpdates.mockResolvedValue(undefined);node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{vi.restoreAllMocks();act(()=>root.unmount());node.remove();clearCache()})
async function openUpdates(){await act(async()=>{Array.from(node.querySelectorAll('button')).find(button=>button.textContent==='View new →')!.click()});for(let i=0;i<100&&!node.querySelector('[role="dialog"]');i++)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,10))})}
async function closeUpdates(){await act(async()=>{(node.querySelector('[aria-label="Close dashboard dialog"]') as HTMLButtonElement).click()})}
async function render(){await act(async()=>root.render(<MemoryRouter><Dashboard/></MemoryRouter>))}
it('puts discoveries above stats and dismisses the unread snapshot',async()=>{
 await render()
 expect(node.textContent).toContain('1 episodes · 1 videos')
 await openUpdates()
 expect(node.textContent).toContain('New episode')
 await closeUpdates()
 expect(node.querySelector('[aria-label="New content"]')!.compareDocumentPosition(node.querySelector('.dashboard-stats')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
 api.fetchContentUpdates.mockResolvedValue({items:[]})
 const close=node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement
 await act(async()=>close.click())
 expect(api.dismissContentUpdates).toHaveBeenCalledWith(['podcast:one','video:two'],before)
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
 await openUpdates()
 expect(node.textContent).toContain('New video')
 await closeUpdates()
 expect(toast).toHaveBeenCalledOnce()
 expect(toast).toHaveBeenCalledWith(expect.objectContaining({title:'New content found · check incomplete',message:expect.stringContaining('1 source(s) unavailable')}))
})

it('keeps dismissed updates hidden across stale polls and remount, but permits genuinely newer content',async()=>{
 await render()
 await act(async()=>{(node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement).click()})
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
 // The server/cache returning old items must not recreate the banner.
 await act(async()=>window.dispatchEvent(new Event('focus')))
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
 act(()=>root.unmount());root=createRoot(node)
 await render()
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
 const newest={...updates[0],item_key:'podcast:new',title:'Actually new',created_at:'2026-10-21T00:00:00.123457+00:00'}
 api.fetchContentUpdates.mockResolvedValue({items:[...updates,newest],dismiss_before:newest.created_at})
 await act(async()=>window.dispatchEvent(new Event('focus')))
 await openUpdates()
 expect(node.textContent).toContain('Actually new')
 await closeUpdates()
 expect(node.textContent).not.toContain('New episode')
})
it('ignores an in-flight old read and prevents duplicate close requests',async()=>{
 await render()
 let finishRead!:(value:any)=>void,finishDismiss!:()=>void
 api.fetchContentUpdates.mockImplementationOnce(()=>new Promise(resolve=>{finishRead=resolve}))
 await act(async()=>window.dispatchEvent(new Event('focus')))
 api.dismissContentUpdates.mockImplementationOnce(()=>new Promise(resolve=>{finishDismiss=resolve}))
 const close=node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement
 await act(async()=>{close.click();close.click()})
 expect(api.dismissContentUpdates).toHaveBeenCalledTimes(1)
 await act(async()=>finishDismiss())
 await act(async()=>finishRead({items:updates,dismiss_before:before}))
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
})
it('keeps updates and offers retry feedback if saving dismissal fails',async()=>{
 api.dismissContentUpdates.mockRejectedValueOnce(new Error('Offline'))
 await render()
 await act(async()=>{(node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement).click()})
 await openUpdates()
 expect(node.textContent).toContain('New episode')
 await closeUpdates()
 expect(localStorage.getItem('xyz_pref:owner:content_updates_dismissed_before')).toBeNull()
 expect(toast).toHaveBeenCalledWith(expect.objectContaining({title:'Could not dismiss updates'}))
})

it('dismisses microsecond timestamps with browsers that only parse millisecond ISO dates',async()=>{
 const parse=Date.parse
 vi.spyOn(Date,'parse').mockImplementation(value=>/\.\d{4,}/.test(value)?NaN:parse(value))
 await render()
 await act(async()=>{(node.querySelector('[aria-label="Dismiss these updates"]') as HTMLButtonElement).click()})
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
 await act(async()=>window.dispatchEvent(new Event('focus')))
 expect(node.querySelector('[aria-label="New content"]')).toBeNull()
})
