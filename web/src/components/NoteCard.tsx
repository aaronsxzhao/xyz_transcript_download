import {Link} from 'react-router-dom'
import CachedImage from './CachedImage'
import {prefetchSummary,prefetchVideoNote,cancelPrefetch} from '../lib/summaryPrefetch'

type Item={id:string;kind:'podcast'|'video';title:string;source?:string;thumbnail?:string;topics_count?:number;progress?:number}
export default function NoteCard({item,reading=false,priority=false}:{item:Item;reading?:boolean;priority?:boolean}) {
  const prefetch=()=>item.kind==='podcast'?prefetchSummary(item.id):prefetchVideoNote(item.id)
  return <Link className="reading-history-card" data-kind={item.kind} to={item.kind==='podcast'?`/viewer/${item.id}`:`/videos/${item.id}`} onPointerEnter={prefetch} onFocus={prefetch} onPointerLeave={cancelPrefetch} onBlur={cancelPrefetch}>
    <CachedImage priority={priority} src={item.thumbnail||''} alt="" className="reading-history-art" fit={item.kind==='podcast'?'contain':'cover'}/>
    <div className="min-w-0 flex-1"><h3 className="font-medium line-clamp-2">{item.title}</h3><p className="text-sm text-gray-400 truncate mt-1">{item.source|| (item.kind==='podcast'?'Podcast':'Video')}</p>
      <p className="text-xs text-indigo-300 mt-2">{reading?(item.progress||0)>=95?'Read again':item.progress?`${item.progress}% read · Resume`:'Resume reading':item.topics_count?`${item.topics_count} topics · Read summary`:'Read summary →'}</p>
      {reading&&<progress aria-label={`${item.title} reading progress`} value={item.progress||0} max={100}/>}
    </div>
  </Link>
}
