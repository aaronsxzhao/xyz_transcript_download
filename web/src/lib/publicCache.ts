import { reloadFreshPage } from './chunkRecovery'

let updateReady = false
export const hasWebsiteUpdate = () => updateReady
export const applyWebsiteUpdate = reloadFreshPage

/** Cache public program files; account data remains in the normal authenticated path. */
export function registerPublicCache() {
  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return
  let controlled = !!navigator.serviceWorker.controller
  const showUpdate = () => {
    updateReady = true
    window.dispatchEvent(new Event('xyz:website-update'))
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
    void navigator.serviceWorker.register('/sw.js', {scope:'/', updateViaCache:'none'}).then(registration => {
      let checkedAt = Date.now()
      const check = () => {
        if (document.visibilityState === 'hidden' || Date.now() - checkedAt < 60000) return
        checkedAt = Date.now()
        void registration.update().catch(() => {})
      }
      window.addEventListener('focus', check)
      document.addEventListener('visibilitychange', check)
    }).catch(() => {})
  }, 1500)
}
