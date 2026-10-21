// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {getCache,setCache,clearCache} from '../src/lib/cache'
import {useRecordReading,useVerifiedReading,type ReadingEntry} from '../src/lib/readingHistory'
import {fetchLibrary} from '../src/lib/api'
vi.mock('../src/lib/api',async load=>({...await load<object>(),fetchLibrary:vi.fn()}))
let root:ReturnType<typeof createRoot>,node:HTMLElement
beforeEach(()=>{localStorage.clear();sessionStorage.clear();clearCache();node=document.createElement('main');document.body.append(node);root=createRoot(node);vi.clearAllMocks()})
afterEach(()=>{act(()=>root.unmount());node.remove();clearCache()})
function Reader({ready}:{ready:boolean}){useRecordReading({id:'one',kind:'podcast',title:'Saved note'},ready);return <p>Note</p>}
function History(){const {items}=useVerifiedReading();return <p>{items.map(i=>i.title).join(',')}</p>}
it('records actual readable visits, not pending or invalid pages',async()=>{
 await act(async()=>root.render(<Reader ready={false}/>));expect(getCache('reading_history')).toBeNull()
 await act(async()=>root.render(<Reader ready/>));expect(getCache<ReadingEntry[]>('reading_history')?.[0]).toMatchObject({id:'one',kind:'podcast',title:'Saved note',position:0})
})
it('verifies ownership and readiness before showing saved history',async()=>{
 setCache('reading_history',[{id:'one',kind:'podcast',title:'Old title',progress:35,lastRead:10},{id:'missing',kind:'video',title:'Unavailable',progress:2,lastRead:9}])
 vi.mocked(fetchLibrary).mockResolvedValue({items:[{id:'one',kind:'podcast',title:'Verified note',source:'Show',date:'',status:'completed'}],next_cursor:null})
 await act(async()=>root.render(<History/>))
 expect(node.textContent).toBe('Verified note');expect(node.textContent).not.toContain('Unavailable')
 expect(fetchLibrary).toHaveBeenCalledWith(expect.stringContaining('ids=podcast%3Aone%2Cvideo%3Amissing'),'',expect.any(AbortSignal))
})

it('offers recovery when reading references cannot be verified',async()=>{
 setCache('reading_history',[{id:'one',kind:'podcast',title:'Old note',progress:12,lastRead:10}])
 vi.mocked(fetchLibrary).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({items:[],next_cursor:null})
 function Status(){const {status,retry}=useVerifiedReading();return <><p>{status}</p><button onClick={retry}>Retry history</button></>}
 await act(async()=>root.render(<Status/>));expect(node.textContent).toContain('error')
 await act(async()=>node.querySelector('button')!.click());expect(node.textContent).toContain('ready')
 expect(fetchLibrary).toHaveBeenCalledTimes(2)
})
