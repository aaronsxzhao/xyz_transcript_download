import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { authFetch } from '../lib/api'
import { clearCache } from '../lib/cache'
import { getAuthGeneration } from '../lib/auth'
import { requestWithDeadline } from '../lib/requestDeadline'

type Repair = { status: string; message?: string; missing?: number }
export async function downloadArchive(path: string, filename: string): Promise<string> {
  const generation=getAuthGeneration()
  const {blob,missing}=await requestWithDeadline(async signal=>{
    const response = await authFetch(path,{signal})
    if (!response.ok) {
      let detail=''
      try {const body=await response.json();if(typeof body.detail==='string')detail=body.detail}catch{/* Proxy failures may contain HTML instead of JSON. */}
      throw new Error(detail || `Backup download failed (HTTP ${response.status}). Please retry.`)
    }
    const blob=await response.blob()
    const header=new Uint8Array(await blob.slice(0,4).arrayBuffer())
    if(header[0]!==0x50||header[1]!==0x4b||!((header[2]===3&&header[3]===4)||(header[2]===5&&header[3]===6)||(header[2]===7&&header[3]===8)))
      throw new Error('The server did not return a ZIP backup. Please retry; no backup file was downloaded.')
    if(generation!==getAuthGeneration())throw new DOMException('Account changed while preparing download.','AbortError')
    return {blob,missing:Number(response.headers.get('X-Missing-Images')||0)}
  },{timeout:180000,retry:false,message:'Backup preparation timed out. Try downloading individual notes, or retry the library backup later.'})
  if(generation!==getAuthGeneration())throw new DOMException('Account changed while preparing download.','AbortError')
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = filename
  document.body.append(link)
  try{link.click()}finally{link.remove();setTimeout(() => URL.revokeObjectURL(url), 30000)}
  return missing ? `Downloaded. ${missing} unavailable images are listed in manifest.json.` : 'Downloaded with all referenced images.'
}
const button = 'px-3 py-2 text-sm rounded-lg bg-dark-hover border border-dark-border disabled:opacity-50'

export function NoteRecovery({ id, version = '', warning = '', failed = false, local = false, expanded = false, onRestored }: { id: string; version?: string; warning?: string; failed?: boolean; local?: boolean; expanded?: boolean; onRestored?: () => void }) {
  const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const currentId = useRef(id); currentId.current = id
  const restoredRef = useRef(onRestored); restoredRef.current = onRestored
  const [repair, setRepair] = useState<Repair | null>(null)
  const base = `/api/maintenance/notes/${encodeURIComponent(id)}`
  useEffect(() => {
    setMessage(''); setError(''); setRepair(null); setBusy(false)
  }, [id])
  useEffect(() => {
    if (repair?.status !== 'running') return
    let stopped = false
    const generation=getAuthGeneration()
    const current=()=>!stopped && generation===getAuthGeneration()
    const controller=new AbortController()
    let timer:ReturnType<typeof setTimeout>
    const poll=async()=>{
      try {
        const next=await requestWithDeadline(async signal=>{
          const r=await authFetch(base + '/repair-media',{signal})
          if (!r.ok) throw new Error('Could not check screenshot repair. You can retry later.')
          return await r.json() as Repair
        },{signal:controller.signal,timeout:15000,message:'Could not check screenshot repair. Retrying status shortly.'})
        if (current()) { setError('');setRepair(next); if (next.status === 'completed') { clearCache(); setMessage(''); restoredRef.current?.() } }
      }catch(e){if(current())setError(e instanceof Error?e.message:'Could not check screenshot repair.')}
      finally{if(current())timer=setTimeout(()=>void poll(),4000)}
    }
    timer=setTimeout(()=>void poll(),4000)
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [base, repair?.status])
  async function run(action: () => Promise<void>) {
    const note = id, generation = getAuthGeneration()
    const current = () => currentId.current === note && generation === getAuthGeneration()
    setBusy(true); setError('')
    try { await action() } catch (e) { if (current()) setError(e instanceof Error ? e.message : 'Please retry') } finally { if (current()) setBusy(false) }
  }
  async function startRepair(source = '') {
    const note=id, generation=getAuthGeneration()
    // A lost POST acknowledgement does not mean the repair failed. Reconcile
    // through the read-only status endpoint, never automatically submit twice.
    try {
      const data = await requestWithDeadline(async signal => {
        const r = await authFetch(base + '/repair-media', {method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({source_path:source})})
        if (!r.ok) {
          let detail=''
          try { detail=(await r.json()).detail || '' } catch { /* HTML proxy response. */ }
          throw new Error(detail || `Cannot start screenshot repair (HTTP ${r.status}).`)
        }
        return await r.json() as Repair
      }, {timeout:20000,retry:false,message:'Repair confirmation timed out. Checking whether it started…'})
      if(currentId.current===note && generation===getAuthGeneration()) setRepair(data)
    } catch(error) {
      if(currentId.current===note && generation===getAuthGeneration())
        setRepair({status:'running',message:'Checking whether screenshot repair started…'})
      throw error
    }
  }
  return <section aria-label="Note recovery and backup" className="mb-3 text-sm space-y-2">
    {warning && <p role="status" className="text-amber-300">The summary is saved. {warning}</p>}
    <details data-screenshot-recovery open={expanded || failed || !!warning || undefined}><summary className="cursor-pointer text-gray-400 py-1">Downloads & screenshot recovery</summary><div className="flex flex-wrap gap-2 pt-2">
      <button className={button} disabled={busy} onClick={() => void run(async () => setMessage(await downloadArchive(base + '/bundle' + (version ? `?version=${encodeURIComponent(version)}` : ''), 'note-with-images.zip')))}>Download with images</button>
      <button className={button} disabled={busy || repair?.status === 'running'} onClick={() => void run(() => startRepair())}>{repair?.status === 'running' ? 'Restoring screenshots…' : 'Repair screenshots'}</button>
      {failed && <button className={button} disabled={busy} onClick={() => void run(async () => {
        const r = await authFetch(base + '/retry-save', {method:'POST'}); const data = await r.json()
        if (!r.ok) throw new Error(data.detail || 'Cannot recover this save')
        clearCache(); setMessage('Saved copy recovered.'); onRestored?.()
      })}>Recover pending save</button>}
      {local && <label className={button + ' cursor-pointer'}>Restore from original video<input className="sr-only" type="file" accept="video/*,.mkv,.flv,.wmv" disabled={busy || repair?.status === 'running'} onChange={e => {
        const file = e.target.files?.[0]; e.target.value = ''; if (!file) return
        void run(async () => { setMessage('Uploading original video…'); const form = new FormData(); form.append('file', file)
          const r = await authFetch('/api/video-notes/upload', {method:'POST',body:form}); const data = await r.json()
          if (!r.ok) throw new Error(data.detail || 'Upload failed'); await startRepair(data.path); setMessage('Original received. Restoring screenshots without regenerating your summary.') })
      }} /></label>}
    </div>
    </details>
    {repair?.status === 'idle' && <p role="status">No active screenshot repair was found. You can retry safely.</p>}
    {repair?.message && <p role={repair.status==='failed'?'alert':'status'} className={repair.status==='failed'?'text-red-300':undefined}>{repair.message}</p>}
    {message && <p role="status" className="text-gray-300">{message}</p>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
  </section>
}

type Integrity = { referenced: number; missing: number; notes: {id:string;title:string;missing:number;source_required:boolean}[] }
export default function DataRecovery() {
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [error, setError] = useState('')
  const [integrity, setIntegrity] = useState<Integrity | null>(null)
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'Please retry') } finally { setBusy(false) }
  }
  return <section className="p-5 bg-dark-surface border border-dark-border rounded-xl space-y-3">
    <h2 className="text-base font-semibold">Library backup & screenshot recovery</h2>
    <p className="text-sm text-gray-400">Download your notes, versions, transcripts and available screenshots. Keep original audio and video files separately. A large library can take a few minutes to prepare.</p>
    <div className="flex flex-wrap gap-3">
      <button className={button} disabled={busy} onClick={() => void run(async () => { setMessage('Preparing private library download…'); setMessage(await downloadArchive('/api/maintenance/backup', 'library-backup.zip')) })}>{busy ? 'Working…' : 'Download library backup'}</button>
      <button className={button} disabled={busy} onClick={() => void run(async () => { setMessage('Checking saved notes and versions…'); const r = await authFetch('/api/maintenance/media-integrity'); const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'Cannot check screenshots'); setIntegrity(data); setMessage('Screenshot check completed.') })}>Check missing screenshots</button>
    </div>
    {message && <p role="status" className="text-sm">{message}</p>}{error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    {integrity && <div className="text-sm space-y-2"><p>{integrity.missing} missing of {integrity.referenced} referenced screenshots across notes and saved versions.</p><ul className="space-y-2 max-h-64 overflow-y-auto">{integrity.notes.map(n => <li key={n.id}><Link className="underline text-indigo-300" to={`/videos/${n.id}`}>{n.title}</Link> — {n.missing} missing{n.source_required ? ' · original video may be needed' : ''}</li>)}</ul></div>}
  </section>
}
