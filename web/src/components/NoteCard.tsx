import {Link} from 'react-router-dom'
import {FileText,Radio,Video} from 'lucide-react'
import CachedImage from './CachedImage'
import {prefetchSummary,prefetchVideoNote,cancelPrefetch} from '../lib/summaryPrefetch'

type Item={id:string;kind:'podcast'|'video';content_type?:'article'|'audio'|'video';title:string;source?:string;thumbnail?:string;topics_count?:number;progress?:number;date?:string;published_at?:string}
export default function NoteCard({item,reading=false,priority=false}:{item:Item;reading?:boolean;priority?:boolean}) {
  const prefetch=()=>item.kind==='podcast'?prefetchSummary(item.id):prefetchVideoNote(item.id)
  const article=item.content_type==='article'
  const Icon=article?FileText:item.kind==='podcast'||item.content_type==='audio'?Radio:Video
  const saved=item.date && Number.isFinite(Date.parse(item.date)) ? new Date(item.date).toLocaleDateString() : ''
  return <Link className="reading-history-card" data-kind={item.kind} to={item.kind==='podcast'?`/viewer/${item.id}`:`/videos/${item.id}`} onPointerEnter={prefetch} onFocus={prefetch} onPointerLeave={cancelPrefetch} onBlur={cancelPrefetch}>
    <CachedImage priority={priority} src={item.thumbnail||''} alt="" className="reading-history-art" fit={item.kind==='podcast'?'contain':'cover'} fallback={<span className="cached-image-fallback note-card-fallback" data-type={article?'article':item.kind==='podcast'?'audio':'video'} aria-hidden="true"><Icon size={24}/></span>}/>
    <div className="min-w-0 flex-1"><h3 className="font-medium line-clamp-2">{item.title}</h3><p className="text-sm text-gray-400 truncate mt-1">{item.source|| (item.kind==='podcast'?'Podcast':'Video')}</p>
      {!reading&&<p className="note-card-meta"><span>{article?'Article':item.kind==='podcast'?'Podcast':item.content_type==='audio'?'Audio':'Video'}</span>{item.published_at&&<time dateTime={item.published_at}>Published {item.published_at.slice(0,10)}</time>}{saved&&<time dateTime={item.date} title="Date saved to your library">Saved {saved}</time>}</p>}
      <p className="text-xs text-indigo-300 mt-2">{reading?(item.progress||0)>=95?'Read again':item.progress?`${item.progress}% read · Resume`:'Resume reading':article?'Read article →':item.topics_count?`${item.topics_count} topics · Read summary`:'Read summary →'}</p>
      {reading&&<progress aria-label={`${item.title} reading progress`} value={item.progress||0} max={100}/>}
    </div>
  </Link>
}
