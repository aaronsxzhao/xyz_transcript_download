// @vitest-environment jsdom
import {webcrypto} from 'node:crypto'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {mapCacheKey,prepareMindMap} from '../src/lib/mindmapCache'
import {buildMapOutline} from '../src/lib/mindmapOutline'
import {clearCache} from '../src/lib/cache'

const first='# Markdown examples\n\nUse `![first](first.png)` in the source.'
const second='# Markdown examples\n\nUse `![second](second.png)` in the source.'
class MapWorker {
 onmessage:((event:{data:unknown})=>void)|null=null
 onerror:(()=>void)|null=null
 postMessage(markdown:string){queueMicrotask(()=>this.onmessage?.({data:{outline:buildMapOutline(markdown)}}))}
 terminate(){}
}
beforeEach(()=>{localStorage.clear();clearCache();vi.stubGlobal('crypto',webcrypto);vi.stubGlobal('Worker',MapWorker)})
afterEach(()=>{clearCache();vi.restoreAllMocks();vi.unstubAllGlobals()})

it('distinguishes image syntax that is literal text inside inline code',async()=>{
 expect(buildMapOutline(first)).not.toEqual(buildMapOutline(second))
 expect(await mapCacheKey(first)).not.toBe(await mapCacheKey(second))
})

it('does not reuse another note outline when only literal image syntax changed',async()=>{
 const worker=vi.spyOn(MapWorker.prototype,'postMessage')
 const signal=new AbortController().signal
 const rendered=await prepareMindMap(first,signal)
 rendered.root.content='Changed by renderer'
 expect(await prepareMindMap(first,signal)).toEqual(buildMapOutline(first))
 expect(worker).toHaveBeenCalledTimes(1)
 expect(await prepareMindMap(second,signal)).toEqual(buildMapOutline(second))
 expect(worker).toHaveBeenCalledTimes(2)
})
