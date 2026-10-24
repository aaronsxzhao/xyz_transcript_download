import {useRef,useState} from 'react'
import {Loader2,Upload} from 'lucide-react'
import {uploadLocalPodcastAudio,type LocalAudioUploadResult} from '../lib/api'
import {getAccountId} from '../lib/preferences'
import {useToast} from './Toast'

export default function LocalPodcastUpload({onUploaded}:{onUploaded:(result:LocalAudioUploadResult)=>void}) {
  const [uploading,setUploading]=useState(false)
  const [title,setTitle]=useState('')
  const [description,setDescription]=useState('')
  const input=useRef<HTMLInputElement>(null)
  const busy=useRef(false)
  const {addToast}=useToast()
  async function upload(file:File) {
    if(busy.current)return
    busy.current=true;setUploading(true)
    const owner=getAccountId()
    try {
      const result=await uploadLocalPodcastAudio(file,{title:title.trim(),description:description.trim()})
      if(owner!==getAccountId())return
      onUploaded(result)
      setTitle('');setDescription('')
      addToast({type:'success',title:'Audio uploaded',message:result.episode.title})
    } catch(error) {
      if(owner===getAccountId())addToast({type:'error',title:'Upload failed',message:error instanceof Error?error.message:'Please retry.'})
    } finally {
      busy.current=false;setUploading(false)
      // A rejected upload must allow selecting the same file again.
      if(input.current)input.current.value=''
    }
  }
  return <section className="p-4 bg-dark-surface border border-dark-border rounded-xl space-y-4" aria-label="Upload local podcast audio">
    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div><h2 className="text-base font-semibold text-white">Add More Local Audio</h2><p className="text-sm text-gray-400">New uploads are added to this local podcast and can be processed like normal episodes.</p></div>
      <button onClick={()=>input.current?.click()} disabled={uploading} className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors">
        {uploading?<Loader2 size={16} className="animate-spin"/>:<Upload size={16}/>} Upload Audio
      </button>
    </div>
    <div className="grid gap-3 md:grid-cols-2">
      <input type="text" aria-label="Audio title" disabled={uploading} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Optional title override" className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"/>
      <input ref={input} type="file" aria-label="Local audio file" accept="audio/*,.mp3,.m4a,.wav,.aac,.flac,.ogg,.opus,.mp4,.mpeg,.mpga" className="hidden" disabled={uploading} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file)}}/>
      <textarea aria-label="Audio description" disabled={uploading} value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional description" rows={2} className="md:col-span-2 w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base resize-y"/>
    </div>
  </section>
}
