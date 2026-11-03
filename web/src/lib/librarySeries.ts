import type {LibraryItem} from './api'
export function seriesIdentity(item:LibraryItem) {
  if(item.kind!=='video'||item.platform!=='bilibili'||!item.source_url)return null
  try {
    const url=new URL(item.source_url)
    if(!['bilibili.com','www.bilibili.com','m.bilibili.com'].includes(url.hostname))return null
    const id=url.pathname.match(/^\/video\/(BV\w+|av\d+)\/?$/)?.[1]
    const title=item.title.match(/^(.*?) · P(\d+)\/(\d+)\s*(.*)$/)
    const part=Number(url.searchParams.get('p')||title?.[2]||1)
    if(!id||!Number.isInteger(part)||part<1)return null
    return {id,part,total:Number(title?.[3]||0),title:title?.[1]||item.title,label:title?.[4]||item.title}
  } catch{return null}
}
export type LibrarySeries={key:string;title:string;total:number;series:boolean;items:LibraryItem[]}
export function groupLibrarySeries(items:LibraryItem[]):LibrarySeries[] {
  const rows:LibrarySeries[]=[], groups=new Map<string,LibrarySeries>()
  for(const item of items){
    const identity=seriesIdentity(item)
    if(!identity){rows.push({key:item.kind+':'+item.id,title:item.title,total:1,series:false,items:[item]});continue}
    let group=groups.get(identity.id)
    if(!group){group={key:'series:'+identity.id,title:identity.title,total:identity.total,series:identity.total>1||identity.part>1,items:[]};groups.set(identity.id,group);rows.push(group)}
    group.items.push(item)
    group.total=Math.max(group.total,identity.total)
    if(identity.total>1)group.title=identity.title
    group.series ||= identity.total>1||identity.part>1||new Set(group.items.map(i=>seriesIdentity(i)?.part)).size>1
  }
  for(const group of rows)if(group.series)group.items.sort((a,b)=>(seriesIdentity(a)?.part||1)-(seriesIdentity(b)?.part||1))
  return rows
}
