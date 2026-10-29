import {useLayoutEffect, useRef, useState} from 'react'
import {setAppearance, useAppearance, type Design} from '../lib/theme'

/** Device-local appearance; independent of account and page form state. */
export default function AppearanceControls() {
  const {design, theme} = useAppearance()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const restoreFocus = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    if (busy) return
    const target = restoreFocus.current
    restoreFocus.current = null
    // Disabling a native select blurs it. Restore only if the user did not
    // deliberately focus another control while the skin was loading.
    if (target?.isConnected && document.activeElement === document.body) target.focus()
  }, [busy])
  async function change(nextDesign: Design, nextTheme: 'dark' | 'light') {
    restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setBusy(true); setError('')
    try { await setAppearance(nextDesign, nextTheme) }
    catch { setError('Appearance unavailable. Reload to retry.') }
    finally { setBusy(false) }
  }
  return <div className="appearance-controls" role="group" aria-label="Appearance" aria-busy={busy}>
    <select aria-label="Interface style" disabled={busy} value={design} onChange={e => void change(e.target.value as Design, theme)}>
      <option value="classic">Classic</option>
      <option value="editorial">A · Editorial</option>
    </select>
    <button type="button" disabled={busy} onClick={() => void change(design, theme === 'dark' ? 'light' : 'dark')}
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
      <span aria-hidden="true">{busy ? '…' : theme === 'dark' ? '☀' : '◐'}</span>
    </button>
    {busy && <span role="status" className="sr-only">Loading appearance…</span>}
    {error && <span className="appearance-error" role="alert">{error}</span>}
  </div>
}
