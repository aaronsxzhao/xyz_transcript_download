// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Podcasts from '../src/pages/Podcasts'
import Library from '../src/pages/Library'
import {detectPodcastPlatform} from '../src/lib/contentLinks'
import {clearCache} from '../src/lib/cache'

const api=vi.hoisted(()=>({fetchPodcasts:vi.fn(),fetchLibrary:vi.fn()}))
vi.mock('../src/lib/api',async load=>({...await load<object>(),...api}))
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:vi.fn(),removeToast:vi.fn()})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('../src/lib/reading',()=>({useReadingPosition:()=>{}}))
vi.mock('../src/lib/readingHistory',()=>({useReadingHistory:()=>[]}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();clearCache();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache()})

it('keeps Spotify and Apple subscriptions in separate categories',async()=>{
 api.fetchPodcasts.mockResolvedValue(['apple','spotify','xiaoyuzhou','local'].map(platform=>({pid:platform,platform,title:'Show '+platform,episode_count:1,summarized_count:0})))
 await act(async()=>root.render(<MemoryRouter initialEntries={['/podcasts?platform=apple']}><Podcasts/></MemoryRouter>))
 await vi.waitFor(()=>expect(node.textContent).toContain('Show apple'))
 expect(node.textContent).not.toContain('Show spotify')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.includes('Spotify'))!.click())
 expect(node.textContent).toContain('Show spotify')
 expect(node.textContent).not.toContain('Show apple')
})

it('labels every supported podcast, video and social source explicitly in Library',async()=>{
 const platforms=['xiaoyuzhou','apple','spotify','local','youtube','bilibili','douyin','kuaishou','twitter','substack']
 api.fetchLibrary.mockResolvedValue({items:platforms.map((platform,i)=>({id:String(i),kind:i<4?'podcast':'video',platform,title:'Note '+platform,source:'Source',status:'completed',date:'2026-10-24'})),next_cursor:null})
 await act(async()=>root.render(<MemoryRouter><Library/></MemoryRouter>))
 await vi.waitFor(()=>expect(node.querySelectorAll('.library-card')).toHaveLength(platforms.length))
 expect([...node.querySelectorAll('.library-card-meta>span')].map(el=>el.textContent)).toEqual(['小宇宙','Apple Podcasts','Spotify','Local Uploads','YouTube','Bilibili','抖音','快手','X / Twitter','Substack'])
})

it.each([
 ['https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ','spotify'],
 ['https://podcasts.apple.com/podcast/id123','apple'],
 ['https://www.xiaoyuzhoufm.com/podcast/123','xiaoyuzhou'],
 ['https://podcasts.apple.com.evil.example/podcast/id123',''],
 ['https://example.com/?next=https://open.spotify.com/episode/123',''],
])('recognizes podcast origin from %s', (url,platform)=>expect(detectPodcastPlatform(url)).toBe(platform))
