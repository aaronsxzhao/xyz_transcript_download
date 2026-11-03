import type {VideoTask} from './api'

/** Use the source identity, never similar course titles, to group parts. */
export function collectionIdentity(task: VideoTask) {
  if (task.platform !== 'bilibili') return null
  try {
    const url = new URL(task.url)
    if (!['www.bilibili.com','bilibili.com','m.bilibili.com'].includes(url.hostname)) return null
    const id = url.pathname.match(/^\/video\/((?:BV[\w]+)|(?:av\d+))\/?$/)?.[1]
    if (!id) return null
    const match = task.title.match(/^(.*?) · P(\d+)\/(\d+)\s*(.*)$/)
    const metadata = task.source_metadata
    const page = metadata?.bilibili_part?.page || Number(url.searchParams.get('p') || 1)
    const total = metadata?.bilibili_parts?.length || Number(match?.[3] || 0)
    if (!Number.isInteger(page) || page < 1) return null
    return {key:id,page,total,title:match?.[1] || task.title}
  } catch { return null }
}

export function groupVideoCollections(tasks: VideoTask[]) {
  const groups: {key:string;title:string;total:number;collection:boolean;tasks:VideoTask[]}[] = []
  const bySource = new Map<string, typeof groups[number]>()
  for (const task of tasks) {
    const source = collectionIdentity(task)
    if (!source) { groups.push({key:task.id,title:task.title,total:1,collection:false,tasks:[task]}); continue }
    let group = bySource.get(source.key)
    if (!group) {
      group = {key:source.key,title:source.title,total:source.total,collection:source.total>1,tasks:[]}
      bySource.set(source.key,group); groups.push(group)
    }
    group.tasks.push(task)
    if (source.total > group.total) {group.total=source.total;group.title=source.title}
    group.collection ||= source.total>1 || new Set(group.tasks.map(row=>collectionIdentity(row)?.page)).size>1
  }
  for (const group of groups) if (group.collection) group.tasks.sort((a,b)=>(collectionIdentity(a)?.page || 1)-(collectionIdentity(b)?.page || 1))
  return groups
}

export function partLabel(title:string) {
  return title.replace(/^.*? · P\d+\/\d+\s*/, '') || title
}
