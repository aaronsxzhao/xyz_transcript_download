import {useRef,useState} from 'react'
import {Search,Trash2,Loader2,AlertTriangle,CheckCircle} from 'lucide-react'
import {authFetch,parseApiResponseAsJson} from '../lib/api'
import {getAccountId} from '../lib/preferences'

interface TruncatedItem {
  episode_id: string
  pid: string
  episode_title: string
  episode_duration: number
  transcript_duration: number
  percentage: number
}

export default function TranscriptMaintenance() {
  const [truncatedItems, setTruncatedItems] = useState<TruncatedItem[]>([])
  const [checking, setChecking] = useState(false)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<{message:string;failed:boolean} | null>(null)
  const [cleanupReady,setCleanupReady] = useState(false)
  const maintenanceBusy = useRef(false)
  async function checkTruncated() {
    if (maintenanceBusy.current) return
    maintenanceBusy.current=true
    const owner=getAccountId()
    setChecking(true);setCleanupReady(false);setCleanupResult(null)
    try {
      const response=await authFetch('/api/truncated')
      const data=await parseApiResponseAsJson<{truncated:TruncatedItem[]}>(response,'Could not check transcripts')
      if (!Array.isArray(data.truncated)) throw new Error('The server returned an incomplete transcript check. Please retry.')
      if (owner!==getAccountId()) return
      setTruncatedItems(data.truncated);setCleanupReady(true)
      if (!data.truncated.length) setCleanupResult({message:'No truncated transcripts found.',failed:false})
    } catch (error) {
      if (owner===getAccountId()) setCleanupResult({message:'Failed to check transcripts: '+(error instanceof Error?error.message:'Please retry.'),failed:true})
    } finally { maintenanceBusy.current=false; if(owner===getAccountId())setChecking(false) }
  }

  async function cleanupTruncated() {
    if (maintenanceBusy.current || !cleanupReady || !truncatedItems.length) return
    if (!confirm(`This will delete the ${truncatedItems.length} listed truncated transcripts and their summaries. Continue?`)) return
    maintenanceBusy.current=true
    const owner=getAccountId()
    setCleaning(true);setCleanupReady(false);setCleanupResult(null)
    try {
      const response=await authFetch('/api/truncated/cleanup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({episode_ids:truncatedItems.map(item=>item.episode_id)})})
      const data=await parseApiResponseAsJson<{deleted:{episode_id:string;deleted_transcript:boolean}[];failed?:{episode_id:string;detail:string}[];skipped?:string[]}>(response,'Could not confirm cleanup')
      if (!Array.isArray(data.deleted) || data.failed!==undefined&&!Array.isArray(data.failed) || data.skipped!==undefined&&!Array.isArray(data.skipped)) throw new Error('The server returned an incomplete cleanup result.')
      if(owner!==getAccountId())return
      const confirmed=data.deleted.filter(item=>item.deleted_transcript===true)
      const failed=new Set([...(data.failed||[]).map(item=>item.episode_id),...data.deleted.filter(item=>item.deleted_transcript!==true).map(item=>item.episode_id)])
      const removed=new Set([...confirmed.map(item=>item.episode_id),...(data.skipped||[])])
      setTruncatedItems(previous=>previous.filter(item=>!removed.has(item.episode_id)||failed.has(item.episode_id)))
      const details=[...new Set((data.failed||[]).map(item=>item.detail))].join(' ')
      setCleanupResult({failed:failed.size>0,message:`${confirmed.length} transcript deletions confirmed.${data.skipped?.length?` ${data.skipped.length} no longer need cleanup.`:''}${failed.size?` ${failed.size} items need attention. ${details} Check again before retrying.`:' You can reprocess these episodes.'}`})
    } catch (error) {
      if(owner===getAccountId())setCleanupResult({message:'Failed to confirm cleanup: '+(error instanceof Error?error.message:'Please retry.')+' Check again before retrying.',failed:true})
    } finally { maintenanceBusy.current=false;if(owner===getAccountId())setCleaning(false) }
  }

  function formatDuration(seconds: number): string {
    return `${Math.floor(seconds / 60)} min`
  }

  return (
          <section className="p-5 bg-dark-surface border border-dark-border rounded-xl">
            <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
              <Trash2 className="text-red-500" size={18} />
              Data Maintenance
            </h2>
            <p className="text-sm text-gray-400 mb-3">
              Check for truncated transcripts (duration &lt; 85% of expected).
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mb-3">
              <button
                onClick={checkTruncated}
                disabled={checking || cleaning}
                className="flex items-center gap-2 px-4 py-2 bg-dark-hover hover:bg-dark-border text-white rounded-lg transition-colors disabled:opacity-50"
              >
                {checking ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                Check for Truncated
              </button>
              {truncatedItems.length > 0 && (
                <button
                  onClick={cleanupTruncated}
                  disabled={cleaning || checking || !cleanupReady}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50"
                >
                  {cleaning ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  Delete {truncatedItems.length} Truncated
                </button>
              )}
            </div>
            {cleanupResult && (
              <div role={cleanupResult.failed ? 'alert' : 'status'} className={`p-3 rounded-lg mb-3 ${
                cleanupResult.failed
                  ? 'bg-red-500/10 border border-red-500/30 text-red-300'
                  : 'bg-green-500/10 border border-green-500/30 text-green-300'
              }`}>
                <div className="flex items-start gap-2">
                  {cleanupResult.failed ? <AlertTriangle className="shrink-0" size={16} /> : <CheckCircle className="shrink-0" size={16} />}
                  <p className="min-w-0 [overflow-wrap:anywhere]">{cleanupResult.message}</p>
                </div>
              </div>
            )}
            {truncatedItems.length > 0 && (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                <p className="text-sm text-yellow-400 flex items-center gap-2 mb-2">
                  <AlertTriangle size={16} />
                  Found {truncatedItems.length} truncated transcripts:
                </p>
                {truncatedItems.map(item => (
                  <div key={item.episode_id} className="p-3 bg-dark-hover rounded-lg text-sm">
                    <p className="text-white font-medium truncate">{item.episode_title}</p>
                    <p className="text-gray-400 mt-1">
                      Transcript: {formatDuration(item.transcript_duration)} / Expected: {formatDuration(item.episode_duration)}
                      <span className="text-red-400 ml-2">({item.percentage}%)</span>
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>

  )
}
