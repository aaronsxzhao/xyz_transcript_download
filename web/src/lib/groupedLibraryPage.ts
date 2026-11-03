import {fetchLibrary, type LibraryPage} from './api'
import {groupLibrarySeries} from './librarySeries'
import {getAccountId} from './preferences'

/** Fill the existing page after parts collapse into series, with bounded reads. */
export async function fetchGroupedLibraryPage(filters:string, cursor='', signal?:AbortSignal):Promise<LibraryPage> {
  const target=Number(new URLSearchParams(filters).get('limit')||40)
  const owner=getAccountId(), seen=new Set<string>()
  let result:LibraryPage={items:[],next_cursor:cursor||null}
  for(let reads=0;reads<5;reads++) {
    signal?.throwIfAborted()
    if(owner!==getAccountId())throw new Error('Account changed')
    const page=await fetchLibrary(filters,cursor,signal)
    signal?.throwIfAborted()
    if(owner!==getAccountId())throw new Error('Account changed')
    if(!Array.isArray(page.items))throw new Error('Cannot load saved content')
    result={...page,items:[...new Map([...result.items,...page.items].map(item=>[item.kind+':'+item.id,item])).values()]}
    const groups=groupLibrarySeries(result.items)
    if(!page.next_cursor||page.next_cursor===cursor||seen.has(page.next_cursor)||groups.length>=target||groups.length===result.items.length)break
    seen.add(cursor);cursor=page.next_cursor
  }
  return result
}
