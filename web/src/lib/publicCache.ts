/** Cache public program files; account data remains in the normal authenticated path. */
export function registerPublicCache() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return
  let controlled = !!navigator.serviceWorker.controller
  let shown = false
  const showUpdate = () => {
    if (shown) return
    shown = true
    const banner = document.createElement('div')
    banner.className = 'fixed bottom-4 right-4 z-50 bg-dark-surface text-gray-100 border border-dark-border rounded-lg p-3 shadow-lg text-sm'
    banner.setAttribute('role', 'status')
    banner.append('Website update ready. ')
    const button = document.createElement('button')
    button.className = 'text-indigo-300 underline ml-2'
    button.textContent = 'Reload'
    button.onclick = () => location.reload()
    banner.append(button)
    document.body.append(banner)
  }
  navigator.serviceWorker.addEventListener('message', event => {
    if (event.data?.type === 'xyz:update-ready') showUpdate()
  })
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (controlled) showUpdate()
    controlled = true
  })
  // Register after rendering. Installation must never delay the current page.
  window.setTimeout(() => {
    void navigator.serviceWorker.register('/sw.js', {scope:'/', updateViaCache:'none'}).catch(() => {})
  }, 1500)
}
