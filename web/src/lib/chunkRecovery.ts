/** Recover a tab whose lazy page filenames were replaced by a deployment. */
export function recoverPageImport(event: Event) {
  if (!navigator.onLine) return
  try {
    const key = 'xyz_page_reload_at'
    const previous = Number(sessionStorage.getItem(key) || 0)
    if (Date.now() - previous < 60000) return
    // A persistent network failure must reach the error boundary, not loop.
    sessionStorage.setItem(key, String(Date.now()))
  } catch { return }
  event.preventDefault()
  window.location.reload()
}
