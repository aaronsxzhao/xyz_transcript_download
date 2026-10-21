import { useEffect } from 'react'

/** Protect in-app links, browser history and document close without storing secrets. */
export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    let index = history.state?.idx ?? 0
    let restoring = false
    const confirmLeave = () => window.confirm('You have unsaved settings. Leave without saving?')
    const unload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    const click = (e: MouseEvent) => {
      const link = (e.target as Element)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!link || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || link.target === '_blank' || link.hasAttribute('download')) return
      const target = new URL(link.href)
      if (target.pathname === location.pathname && target.search === location.search && target.origin === location.origin) return
      if (!confirmLeave()) { e.preventDefault(); e.stopPropagation() }
    }
    const pop = (e: PopStateEvent) => {
      if (restoring) { restoring = false; e.stopImmediatePropagation(); return }
      const next = e.state?.idx
      if (typeof next !== 'number') return
      if (confirmLeave()) { index = next; return }
      e.stopImmediatePropagation()
      if (next !== index) { restoring = true; history.go(index - next) }
    }
    window.addEventListener('beforeunload', unload)
    document.addEventListener('click', click, true)
    window.addEventListener('popstate', pop, true)
    return () => { window.removeEventListener('beforeunload', unload); document.removeEventListener('click', click, true); window.removeEventListener('popstate', pop, true) }
  }, [dirty])
}
