import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { authFetch } from '../lib/api'
import { clearCache } from '../lib/cache'

type Repair = { status: string; message?: string; missing?: number }
export async function downloadArchive(path: string, filename: string): Promise<string> {
  const response = await authFetch(path)
  if (!response.ok) { const body = await response.json(); throw new Error(body.detail || 'Download failed. Please retry.') }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
  const missing = Number(response.headers.get('X-Missing-Images') || 0)
  return missing ? `Downloaded. ${missing} unavailable images are listed in manifest.json.` : 'Downloaded with all referenced images.'
}
const button = 'px-3 py-2 text-sm rounded-lg bg-dark-hover border border-dark-border disabled:opacity-50'

export function NoteRecovery({ id, version = '', warning = '', failed = false, local = false, onRestored }: { id: string; version?: string; warning?: string; failed?: boolean; local?: boolean; onRestored?: () => void }) {
  const [message, setMessage] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const [repair, setRepair] = useState<Repair | null>(null)
  const base = `/api/maintenance/notes/${encodeURIComponent(id)}`
  useEffect(() => {
    setMessage(''); setError(''); setRepair(null)
  }, [id])
  useEffect(() => {
    if (repair?.status !== 'running') return
    let stopped = false
    const timer = setInterval(() => {
      void authFetch(base + '/repair-media').then(async r => {
        if (!r.ok) throw new Error('Could not check screenshot repair. You can retry later.')
        const next = await r.json()
        if (!stopped) { setRepair(next); if (next.status === 'completed') { clearCache(); setMessage('Screenshots restored.'); onRestored?.() } }
      }).catch(e => { if (!stopped) setError(e.message) })
    }, 4000)
    return () => { stopped = true; clearInterval(timer) }
  }, [base, repair?.status])
  async function run(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'Please retry') } finally { setBusy(false) }
  }
  async function startRepair(source = '') {
    const r = await authFetch(base + '/repair-media', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_path:source})})
    const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'Cannot start screenshot repair'); setRepair(data)
  }
  return <section aria-label="Note recovery and backup" className="mb-3 text-sm space-y-2">
    {warning && <p role="status" className="text-amber-300">The summary is saved. {warning}</p>}
    <details open={failed || !!warning || undefined}><summary className="cursor-pointer text-gray-400 py-1">Downloads & screenshot recovery</summary><div className="flex flex-wrap gap-2 pt-2">
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
    {repair?.message && <p role="status">{repair.message}</p>}
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
