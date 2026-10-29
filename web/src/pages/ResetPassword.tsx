import AppearanceControls from '../components/AppearanceControls'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { clearTokens, requestAuth } from '../lib/auth'

export default function ResetPassword() {
  const [token] = useState(() => {
    const params = new URLSearchParams(window.location.hash.slice(1))
    const value = params.get('type') === 'recovery' ? params.get('access_token') || '' : ''
    return value
  })
  useEffect(() => { window.history.replaceState(null, '', window.location.pathname) }, [])
  const submitting = useRef(false)
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [done, setDone] = useState(false)
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (submitting.current) return
    setError('')
    if (password !== confirm) { setError('Passwords do not match'); return }
    submitting.current = true
    setBusy(true)
    try {
      await requestAuth('password', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ password }) })
      clearTokens(); setDone(true)
    } catch (e) { setError(e instanceof Error ? e.message : 'Please retry') }
    finally { submitting.current = false; setBusy(false) }
  }
  return <main className="auth-page min-h-screen grid place-items-center p-4"><div className="w-full max-w-md bg-dark-surface rounded-xl border border-dark-border p-6 space-y-4">
    <AppearanceControls compact />
    <h1 className="page-title text-2xl font-bold">Reset password</h1>
    {done ? <p role="status">Your password is updated. <a className="underline" href="/login">Sign in</a></p>
      : !token ? <p>This recovery link is missing or expired. <Link className="underline" to="/login?mode=recovery">Request a new recovery link</Link></p>
      : <form aria-busy={busy} onSubmit={submit} className="space-y-4">
        <label className="block">New password<input disabled={busy} className="block w-full mt-1 p-3 bg-dark-bg rounded border border-dark-border" type="password" autoComplete="new-password" minLength={8} maxLength={1024} required value={password} onChange={e => setPassword(e.target.value)} /></label>
        <label className="block">Confirm password<input disabled={busy} className="block w-full mt-1 p-3 bg-dark-bg rounded border border-dark-border" type="password" autoComplete="new-password" minLength={8} required value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
        {error && <p role="alert" className="text-red-300">{error}</p>}
        <button disabled={busy} className="w-full p-3 bg-indigo-600 rounded-lg disabled:opacity-50">{busy ? 'Saving password…' : 'Set new password'}</button>
      </form>}
  </div></main>
}
