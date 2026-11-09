import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { authFetch, assertSessionGeneration } from '../lib/api'
import { getAuthGeneration } from '../lib/auth'
import { requestWithDeadline } from '../lib/requestDeadline'

export default function SummaryExport() {
  const { eid } = useParams()
  const [attempt, setAttempt] = useState(0)
  const [html, setHtml] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    const generation = getAuthGeneration()
    setHtml(''); setError('')
    void requestWithDeadline(async signal => {
      const response = await authFetch(`/api/summaries/${encodeURIComponent(eid || '')}/html`, { signal, cache: 'no-store' })
      if (!response.ok) throw new Error(`Could not open the HTML export (HTTP ${response.status}). Return to the reader to check its status, or retry.`)
      const body = await response.text()
      if (!body.trim() || !response.headers.get('content-type')?.includes('text/html')) throw new Error('The HTML export was incomplete. Please retry.')
      assertSessionGeneration(generation)
      return body
    }, { signal: controller.signal }).then(body => {
      if (!controller.signal.aborted) setHtml(body)
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Could not open the HTML export. Please retry.')
    })
    return () => controller.abort()
  }, [eid, attempt])
  if (html) return <iframe title="Summary HTML export" sandbox="" referrerPolicy="no-referrer" srcDoc={html} className="fixed inset-0 h-full w-full border-0 bg-white" />
  return <main className="min-h-screen bg-dark-bg text-gray-100 p-6">
    {error ? <div role="alert"><p>{error}</p><button className="underline my-4" onClick={() => setAttempt(value => value + 1)}>Retry export</button></div> : <p role="status">Preparing HTML export…</p>}
    <Link className="underline" to={`/viewer/${encodeURIComponent(eid || '')}`}>Return to reader</Link>
  </main>
}
