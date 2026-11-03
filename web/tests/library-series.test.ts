import {expect,it} from 'vitest'
import {groupLibrarySeries,seriesIdentity} from '../src/lib/librarySeries'
import type {LibraryItem} from '../src/lib/api'
const part=(n:number,id='BVcourse'):LibraryItem=>({id:id+n,kind:'video',platform:'bilibili',source_url:`https://www.bilibili.com/video/${id}?p=${n}`,title:`Course · P${n}/21 Lesson ${n}`,source:'Teacher',date:'2026-11-03',status:'completed'})
it('groups a series by source identity and orders episodes numerically, preserving feed position',()=>{
 const groups=groupLibrarySeries([part(19),part(21),part(2),part(1,'BVdifferent')])
 expect(groups).toHaveLength(2);expect(groups[0]).toMatchObject({title:'Course',total:21,series:true})
 expect(groups[0].items.map(i=>seriesIdentity(i)?.part)).toEqual([2,19,21])
})
it('recognizes one loaded episode as a series and keeps one series when more pages arrive',()=>{
 expect(groupLibrarySeries([part(19)])[0].series).toBe(true)
 expect(groupLibrarySeries([part(19),part(21),part(1)])).toHaveLength(1)
})
it('never groups unrelated titles, other platforms or lookalike domains',()=>{
 const rows=[{...part(1),source_url:undefined},{...part(2),source_url:'https://www.bilibili.com.evil.test/video/BVcourse?p=2'},{...part(3),platform:'youtube'}]
 expect(groupLibrarySeries(rows)).toHaveLength(3)
 expect(groupLibrarySeries(rows).every(g=>!g.series)).toBe(true)
})
it('does not turn ordinary single-part Bilibili videos into a series',()=>{
 expect(groupLibrarySeries([{...part(1),title:'One video'}])[0].series).toBe(false)
})
