// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter,Routes,Route} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Episodes from '../src/pages/Episodes'
import {fetchPodcasts} from '../src/lib/api'
import {CacheKeys,clearCache,getCache} from '../src/lib/cache'
import {clearTokens} from '../src/lib/auth'
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:vi.fn()})}))
const episode={eid:'e',pid:'test',title:'An available episode',duration:60,pub_date:'',created_at:'',description:'',status:'pending',has_summary:false,has_transcript:false}
const podcast={pid:'test',title:'A podcast',author:'',description:'',cover_url:'',platform:'xiaoyuzhou',feed_url:'',episode_count:35,summarized_count:0,episode_preview:[episode]}
let cleanup:(()=>void)|undefined
beforeEach(()=>{clearTokens();localStorage.clear();sessionStorage.clear();clearCache();localStorage.setItem('xyz_remember_me','true');localStorage.setItem('xyz_user',JSON.stringify({id:'owner',authenticated:true}));localStorage.setItem('xyz_access_token','synthetic')})
afterEach(()=>{cleanup?.();cleanup=undefined;vi.unstubAllGlobals();clearTokens();clearCache()})
it('populates episode content before returning the podcast list without duplicating it in metadata',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>Response.json([podcast])))
 const rows=await fetchPodcasts()
 expect(rows[0]).not.toHaveProperty('episode_preview')
 expect(getCache(CacheKeys.EPISODES('test'))).toEqual([episode])
 expect(getCache(CacheKeys.PODCASTS)).toEqual(rows)
})
it('delivers late collection content into an open episode page after individual episode requests fail',async()=>{
 let finish!:(value:Response)=>void
 vi.stubGlobal('fetch',vi.fn((url:string)=>url==='/api/podcasts?include_content=12'?new Promise<Response>(resolve=>{finish=resolve}):url.startsWith('/api/podcasts/content?')?Promise.reject(new TypeError('Failed to fetch')):Promise.resolve(Response.json(podcast))))
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 cleanup=()=>{act(()=>root.unmount());node.remove()}
 await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts/test/episodes']}><Routes><Route path="/podcasts/:pid/episodes" element={<Episodes/>}/></Routes></MemoryRouter>))
 expect(node.querySelector('[role="alert"]')).not.toBeNull()
 await act(async()=>{finish(Response.json([podcast]));await Promise.resolve()})
 expect(node.textContent).toContain('An available episode')
 expect(node.querySelector('[role="alert"]')).toBeNull()
 expect(node.textContent).toContain('Load more episodes')
})
