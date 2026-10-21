import {LockKeyhole,ExternalLink} from 'lucide-react'
const labels:Record<string,string>={purchase_required:'Purchase required',login_required:'Sign-in required',restricted:'Source access restricted',unavailable:'Source unavailable'}
export function sourceBlocked(status?:string){return !!status && status in labels}
export default function SourceAccessNotice({status,message,episodeId,warning,compact=false}:{status?:string;message?:string;episodeId?:string;warning?:string;compact?:boolean}){
 if(!sourceBlocked(status)&&!warning)return null
 const title=labels[status||'']||'Incomplete transcript'
 const body=<><p className="mt-2 text-sm text-amber-100/80">{message||warning}</p>{message&&warning&&<p className="mt-2 text-sm text-amber-100/80">{warning}</p>}{episodeId&&/^[a-f0-9]{24}$/i.test(episodeId)&&<a href={`https://www.xiaoyuzhoufm.com/episode/${encodeURIComponent(episodeId)}`} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-sm text-amber-200 underline"><ExternalLink size={14}/>Open original episode</a>}</>
 if(compact)return <details onClick={event=>event.stopPropagation()} className="mt-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-amber-300"><summary className="cursor-pointer text-sm"><LockKeyhole size={14} className="mr-1.5 inline"/>{title}</summary>{body}</details>
 return <div role="alert" className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-200"><h2 className="flex items-center gap-2 font-semibold"><LockKeyhole size={18}/>{title}</h2>{body}</div>
}
