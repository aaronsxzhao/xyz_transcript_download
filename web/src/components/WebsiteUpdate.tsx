import { useEffect, useRef, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import { applyWebsiteUpdate, hasWebsiteUpdate } from '../lib/publicCache'

export default function WebsiteUpdate() {
  const [available, setAvailable] = useState(hasWebsiteUpdate)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const busy = useRef(false)
  const timers = useRef<number[]>([])
  const clearTimers = () => { timers.current.forEach(window.clearTimeout); timers.current = [] }
  useEffect(() => {
    const update = () => setAvailable(hasWebsiteUpdate())
    window.addEventListener('xyz:website-update', update)
    update()
    return () => { window.removeEventListener('xyz:website-update', update); clearTimers() }
  }, [])

  const reload = () => {
    if (busy.current) return
    clearTimers()
    if (!navigator.onLine) { setError("You're offline. Reconnect, then try again."); return }
    busy.current = true
    setPending(true)
    setError('')
    const failed = (message: string) => {
      clearTimers()
      busy.current = false
      setPending(false)
      setError(message)
    }
    // Paint the acknowledgement before handing control to browser navigation.
    timers.current = [
      window.setTimeout(() => {
        try { applyWebsiteUpdate() }
        catch { failed('Could not start the reload. Please try again.') }
      }, 100),
      window.setTimeout(() => failed("Reload hasn't completed. Check your connection and try again."), 10000),
    ]
  }

  if (!available) return null
  return <section aria-label="Website update" className="website-update bg-dark-surface">
    <div role={error ? 'alert' : 'status'} aria-atomic="true">
      <strong>{error ? 'Reload needs attention' : pending ? 'Reloading website…' : 'Website update ready'}</strong>
      <p>{error || (pending ? 'Opening the latest version. Please wait…' : 'Save any edits before reloading.')}</p>
    </div>
    <button onClick={reload} disabled={pending} aria-busy={pending} className="ui-button ui-button-primary">
      {pending ? <Loader2 size={16} className="animate-spin" aria-hidden="true"/> : <RefreshCw size={16} aria-hidden="true"/>}
      {pending ? 'Reloading…' : error ? 'Retry reload' : 'Reload'}
    </button>
  </section>
}
