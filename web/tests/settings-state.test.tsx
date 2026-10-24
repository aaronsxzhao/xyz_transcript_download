// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Settings from '../src/pages/Settings'
import {fetchSettings,updateSettings,testLlmConnection,authFetch} from '../src/lib/api'
import {CacheKeys,setCache,getCache,clearCache} from '../src/lib/cache'
import {getPreference,setPreference} from '../src/lib/preferences'
vi.mock('../src/lib/api',async load=>({...await load<object>(),fetchSettings:vi.fn(),updateSettings:vi.fn(),testLlmConnection:vi.fn(),authFetch:vi.fn()}))
vi.mock('../src/contexts/AuthContext',()=>({useAuth:()=>({authEnabled:true})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
const server=(model='openai/gpt-oss-120b')=>({whisper_mode:'api',whisper_model:'whisper-large-v3',llm_provider:'groq',llm_model:model,transcription_provider:'server',llm_base_url:'',whisper_base_url:'',groq_available:true,check_interval:86400} as any)
const small='openai/gpt-oss-20b'
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.resetAllMocks();localStorage.clear();sessionStorage.clear();clearCache()
 vi.mocked(fetchSettings).mockResolvedValue(server())
 vi.mocked(updateSettings).mockResolvedValue({message:'Saved',settings:server(small)})
 vi.mocked(testLlmConnection).mockResolvedValue({message:'Connected',model:small})
 vi.stubGlobal('confirm',()=>true)
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers();vi.unstubAllGlobals();clearCache()})
const button=(label:string)=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()===label)!
const model=()=>node.querySelector<HTMLSelectElement>('[aria-label="Summary model"]')!
async function mount(cached=true){if(cached)setCache(CacheKeys.SETTINGS,server());await act(async()=>root.render(<MemoryRouter><Settings/></MemoryRouter>))}
async function choose(value:string){await act(async()=>{model().value=value;model().dispatchEvent(new Event('change',{bubbles:true}))})}
async function click(label:string){await act(async()=>button(label).click());await act(async()=>vi.dynamicImportSettled())}

it('preserves an edited model when the background settings refresh arrives late',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(fetchSettings).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount();await choose(small);await act(async()=>finish(server()))
 expect(model().value).toBe(small);expect(node.textContent).toContain('Unsaved changes')
})
it.each(['resolve','reject'])('ignores an obsolete settings read after a confirmed save (%s)',async outcome=>{
 let finish!:(value:any)=>void,fail!:(value:Error)=>void
 vi.mocked(fetchSettings).mockImplementationOnce(()=>new Promise((resolve,reject)=>{finish=resolve;fail=reject}))
 await mount();await choose(small);await click('Save Settings')
 await act(async()=>{if(outcome==='resolve')finish(server());else fail(new Error('Old connection failure'))})
 expect(model().value).toBe(small);expect(node.textContent).not.toContain('Old connection failure')
 expect(getCache<any>(CacheKeys.SETTINGS)?.llm_model).toBe(small)
})
it('retains changes made while saving and marks only the submitted values as saved',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(updateSettings).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount();await choose(small);await click('Save Settings');await click('教程 Tutorial')
 await act(async()=>finish({message:'Saved',settings:server(small)}))
 expect(node.textContent).toContain('Unsaved changes');expect(button('Save Settings').disabled).toBe(false)
 expect(getPreference('vd_style')).toBe('detailed')
 expect(button('教程 Tutorial').getAttribute('aria-pressed')).toBe('true')
})
it('does not mark local video choices made during initial loading as already saved',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(fetchSettings).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount(false);await click('教程 Tutorial');await act(async()=>finish(server()))
 expect(node.textContent).toContain('Unsaved changes');expect(button('Save Settings').disabled).toBe(false)
})
it('keeps the confirmed test-and-save model in the settings cache',async()=>{
 await mount();await choose(small);await click('Test and save summaries')
 expect(getCache<any>(CacheKeys.SETTINGS)?.llm_model).toBe(small)
})
it('prevents a normal save from overlapping a connection test-and-save',async()=>{
 vi.mocked(testLlmConnection).mockImplementationOnce(()=>new Promise(()=>{}))
 await mount();await choose(small);await click('Test and save summaries')
 expect(button('Save Settings').disabled).toBe(true)
})
it('preserves a model selected while the previous model is being tested',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(testLlmConnection).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 await mount();await choose(small);await click('Test and save summaries');await choose('openai/gpt-oss-120b')
 await act(async()=>finish({message:'Connected',model:small}))
 expect(model().value).toBe('openai/gpt-oss-120b');expect(node.textContent).toContain('Unsaved changes')
 expect(getCache<any>(CacheKeys.SETTINGS)?.llm_model).toBe(small)
})
it('does not let an earlier success timer erase a later save failure',async()=>{
 await mount();vi.useFakeTimers();await choose(small);await click('Save Settings')
 vi.mocked(updateSettings).mockRejectedValueOnce(new Error('Unavailable'))
 await choose('openai/gpt-oss-120b');await click('Save Settings')
 await act(async()=>vi.advanceTimersByTimeAsync(3000))
 expect(node.textContent).toContain('Failed to save settings: Unavailable')
})
it('reports a failed maintenance check instead of silently showing nothing',async()=>{
 vi.mocked(authFetch).mockResolvedValue(new Response('Upstream unavailable',{status:503}))
 await mount();await click('Tools & Data');await click('Check for Truncated')
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Upstream unavailable')
})
it('keeps the inspected list after cleanup fails and sends only the reviewed IDs',async()=>{
 vi.mocked(authFetch).mockResolvedValueOnce(Response.json({truncated:[{episode_id:'one',episode_title:'One',episode_duration:100,transcript_duration:20,percentage:20}]}))
  .mockResolvedValueOnce(new Response('Cleanup unavailable',{status:503}))
 await mount();await click('Tools & Data');await click('Check for Truncated');await click('Delete 1 Truncated')
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Cleanup unavailable')
 expect(node.textContent).toContain('Found 1 truncated transcripts')
 expect(JSON.parse(vi.mocked(authFetch).mock.calls[1][1]!.body as string)).toEqual({episode_ids:['one']})
})

it('reports unconfirmed cleanup records without removing them from the reviewed list',async()=>{
 vi.mocked(authFetch).mockResolvedValueOnce(Response.json({truncated:[{episode_id:'one',episode_title:'One',episode_duration:100,transcript_duration:20,percentage:20}]}))
  .mockResolvedValueOnce(Response.json({deleted:[{episode_id:'one',deleted_transcript:false}],failed:[{episode_id:'one',detail:'Could not confirm removal'}]}))
 await mount();await click('Tools & Data');await click('Check for Truncated');await click('Delete 1 Truncated')
 expect(node.querySelector('[role=alert]')?.textContent).toContain('0 transcript deletions confirmed')
 expect(node.querySelector('[role=alert]')?.textContent).toContain('1 items need attention')
 expect(button('Delete 1 Truncated').disabled).toBe(true)
 expect(node.textContent).toContain('Found 1 truncated transcripts')
})
it('does not accept an incomplete successful cleanup response as confirmation',async()=>{
 vi.mocked(authFetch).mockResolvedValueOnce(Response.json({truncated:[{episode_id:'one',episode_title:'One',episode_duration:100,transcript_duration:20,percentage:20}]}))
  .mockResolvedValueOnce(Response.json({}))
 await mount();await click('Tools & Data');await click('Check for Truncated');await click('Delete 1 Truncated')
 expect(node.querySelector('[role=alert]')?.textContent).toContain('incomplete cleanup result')
 expect(node.textContent).toContain('Found 1 truncated transcripts')
})
it('retains maintenance inspection results when switching between settings tabs',async()=>{
 vi.mocked(authFetch).mockResolvedValueOnce(Response.json({truncated:[{episode_id:'one',episode_title:'One',episode_duration:100,transcript_duration:20,percentage:20}]}))
 await mount();await click('Tools & Data');await click('Check for Truncated');await click('General');await click('Tools & Data')
 expect(node.textContent).toContain('Found 1 truncated transcripts')
 expect(button('Delete 1 Truncated').disabled).toBe(false)
})

it.each(['null','{}','"summary"','["summary",null]'])('opens settings safely with an invalid saved format preference: %s',async saved=>{
 setPreference('vd_formats',saved)
 await mount()
 expect(button('AI Summary').getAttribute('aria-pressed')).toBe('true')
 expect(button('Screenshots').getAttribute('aria-pressed')).toBe('true')
})
