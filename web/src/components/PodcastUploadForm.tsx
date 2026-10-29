import {useId, type FormEvent} from 'react'
import {Loader2,Upload} from 'lucide-react'
export default function PodcastUploadForm({audioFile,onFile,title,onTitle,description,onDescription,uploading,onSubmit}:{
  audioFile:File|null;onFile:(file:File|null)=>void;title:string;onTitle:(value:string)=>void;
  description:string;onDescription:(value:string)=>void;uploading:boolean;onSubmit:(event:FormEvent)=>void
}) {
  const id = useId()
  return (
<div className="p-4 md:p-6 bg-dark-surface border border-dark-border rounded-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Upload Local Audio</h2>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor={`${id}-file`} className="block text-sm text-gray-400 mb-2">Audio file</label>
                <input
                  id={`${id}-file`}
                  type="file"
                  accept="audio/*,.mp3,.m4a,.wav,.aac,.flac,.ogg,.opus,.mp4,.mpeg,.mpga"
                  onChange={e => onFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-gray-300 file:mr-4 file:rounded-lg file:border-0 file:bg-indigo-600 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-700"
                />
                {audioFile && <p className="mt-2 text-xs text-gray-500">{audioFile.name}</p>}
              </div>
              <div>
                <label htmlFor={`${id}-title`} className="block text-sm text-gray-400 mb-2">Episode title</label>
                <input
                  id={`${id}-title`}
                  type="text"
                  value={title}
                  onChange={e => onTitle(e.target.value)}
                  placeholder="Optional, defaults to filename"
                  className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base"
                />
              </div>
            </div>
            <div>
              <label htmlFor={`${id}-description`} className="block text-sm text-gray-400 mb-2">Description</label>
              <textarea id={`${id}-description`}
                value={description}
                onChange={e => onDescription(e.target.value)}
                placeholder="Optional notes about this upload"
                rows={3}
                className="w-full px-4 py-3 bg-dark-hover border border-dark-border rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:border-indigo-500 text-base resize-y"
              />
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
              <p className="text-sm text-gray-500">First upload creates your Local Uploads podcast automatically. Later uploads go into the same library section.</p>
              <button
                type="submit"
                disabled={uploading || !audioFile}
                className="flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                Upload
              </button>
            </div>
          </form>
        </div>
  )
}
