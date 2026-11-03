import {expect,it} from 'vitest'
import {groupVideoCollections} from '../src/lib/bilibiliCollection'
import type {VideoTask} from '../src/lib/api'
const task=(id:string,page:number,bv='BVexample')=>({id,url:`https://www.bilibili.com/video/${bv}?p=${page}`,platform:'bilibili',title:`Course · P${page}/21 Chapter ${page}`} as VideoTask)
it('groups by source identity, sorts parts numerically and preserves all tasks',()=>{
 const rows=[task('p10',10),task('other',2,'BVdifferent'),task('p2',2),task('retry',2)]
 const groups=groupVideoCollections(rows)
 expect(groups).toHaveLength(2)
 expect(groups[0]).toMatchObject({title:'Course',total:21,collection:true})
 expect(groups[0].tasks.map(t=>t.id)).toEqual(['p2','retry','p10'])
 expect(rows.map(t=>t.id)).toEqual(['p10','other','p2','retry'])
})
it('does not merge unrelated videos with matching titles or invalid source URLs',()=>{
 const rows=[task('a',1),{...task('b',2),url:'https://evil.example/video/BVexample?p=2'}, {...task('c',3),platform:'youtube'}]
 expect(groupVideoCollections(rows)).toHaveLength(3)
})
it('keeps ordinary single videos standalone and recognizes parts before metadata arrives',()=>{
 const single={...task('single',1),title:'Single',url:'https://www.bilibili.com/video/BVsingle'}
 expect(groupVideoCollections([single])[0].collection).toBe(false)
 const parts=[1,2].map(page=>({...task(`p${page}`,page),title:'Course'}))
 expect(groupVideoCollections(parts)[0].collection).toBe(true)
})

it('groups a legacy short-link P1 with the canonical remaining parts',()=>{
 const first={...task('p1',1),url:'https://b23.tv/legacy',source_metadata:{bilibili_part:{page:1,url:'https://www.bilibili.com/video/BVexample?p=1'}}} as VideoTask
 const groups=groupVideoCollections([task('p2',2),first])
 expect(groups).toHaveLength(1)
 expect(groups[0].tasks.map(t=>t.id)).toEqual(['p1','p2'])
 expect(first.url).toBe('https://b23.tv/legacy')
})
it('does not infer short-link identity from titles or untrusted metadata hosts',()=>{
 const first={...task('p1',1),url:'https://b23.tv/legacy'}
 expect(groupVideoCollections([task('p2',2),first])).toHaveLength(2)
 const bad={...first,source_metadata:{bilibili_part:{page:1,url:'https://bilibili.com.evil.example/video/BVexample?p=1'}}} as VideoTask
 expect(groupVideoCollections([task('p2',2),bad])).toHaveLength(2)
 const canonical={...task('other',1,'BVother'),source_metadata:{bilibili_part:{page:1,url:'https://www.bilibili.com/video/BVexample?p=1'}}} as VideoTask
 expect(groupVideoCollections([task('p2',2),canonical])).toHaveLength(2)
})
