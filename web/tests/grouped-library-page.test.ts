import {beforeEach,expect,it,vi} from 'vitest'
import {fetchLibrary,type LibraryItem} from '../src/lib/api'
import {fetchGroupedLibraryPage} from '../src/lib/groupedLibraryPage'
vi.mock('../src/lib/api',()=>({fetchLibrary:vi.fn()}))
vi.mock('../src/lib/preferences',()=>({getAccountId:()=> 'owner'}))
const part=(n:number):LibraryItem=>({id:String(n),kind:'video',platform:'bilibili',source_url:`https://www.bilibili.com/video/BVseries?p=${n}`,title:`Course · P${n}/21 Lesson`,source:'Course',status:'completed',date:''})
beforeEach(()=>vi.resetAllMocks())
it('fills a collapsed first page with other titles without losing episodes',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:Array.from({length:12},(_,i)=>part(i+1)),next_cursor:'next'})
 vi.mocked(fetchLibrary).mockResolvedValueOnce({items:[part(12),{...part(13),id:'other',platform:'youtube'}],next_cursor:null})
 const page=await fetchGroupedLibraryPage('limit=12')
 expect(page.items).toHaveLength(13);expect(page.next_cursor).toBeNull();expect(fetchLibrary).toHaveBeenCalledTimes(2)
})
it('keeps ordinary pagination unchanged',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValue({items:[{...part(1),platform:'youtube'}],next_cursor:'next'})
 await fetchGroupedLibraryPage('limit=12');expect(fetchLibrary).toHaveBeenCalledOnce()
})
it('bounds large series reads and leaves a usable continuation cursor',async()=>{
 vi.mocked(fetchLibrary).mockImplementation(async(_,cursor)=>({items:[part(Number(cursor||0)*2+1),part(Number(cursor||0)*2+2)],next_cursor:String(Number(cursor||0)+1)}))
 const page=await fetchGroupedLibraryPage('limit=12');expect(fetchLibrary).toHaveBeenCalledTimes(5);expect(page.next_cursor).toBe('5')
})
it('stops a repeated cursor',async()=>{
 vi.mocked(fetchLibrary).mockResolvedValue({items:[part(1),part(2)],next_cursor:'next'})
 await fetchGroupedLibraryPage('limit=12');expect(fetchLibrary).toHaveBeenCalledTimes(2)
})
it('does not continue a cancelled filter request',async()=>{
 const abort=new AbortController()
 vi.mocked(fetchLibrary).mockImplementation(async()=>{abort.abort();return {items:[part(1),part(2)],next_cursor:'next'}})
 await expect(fetchGroupedLibraryPage('limit=12','',abort.signal)).rejects.toThrow();expect(fetchLibrary).toHaveBeenCalledOnce()
})
