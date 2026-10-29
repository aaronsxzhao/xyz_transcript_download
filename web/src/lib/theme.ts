import {retryableStyleLoad} from './styleLoading'
import {useSyncExternalStore} from 'react'

export type ColorTheme = 'light' | 'dark'
export type Design = 'classic' | 'editorial'
const event = 'xyz:appearance'
const listeners = new Set<() => void>()
const subscribe = (listener: () => void) => {
  listeners.add(listener)
  window.addEventListener(event, listener)
  if (listeners.size === 1) window.addEventListener('storage', syncStorage)
  return () => { window.removeEventListener(event, listener); listeners.delete(listener); if (!listeners.size) window.removeEventListener('storage', syncStorage) }
}
function syncStorage(e: StorageEvent) {
  if (e.key === 'xyz:design' || e.key === 'xyz:color-theme' || e.key === null) {
    try {
      if (e.storageArea !== localStorage) return
      void setAppearance(localStorage.getItem('xyz:design') === 'editorial' ? 'editorial' : 'classic', localStorage.getItem('xyz:color-theme') === 'light' ? 'light' : 'dark', false).catch(() => { /* Keep the current usable skin if its replacement cannot load. */ })
    } catch { /* Other tabs may deny storage. */ }
  }
}
export function getColorTheme(): ColorTheme { return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark' }
export function getDesign(): Design { return document.documentElement.dataset.design === 'editorial' ? 'editorial' : 'classic' }
let revision = 0
const skins = {editorial:retryableStyleLoad(() => import('../editorial.css')), classic:retryableStyleLoad(() => import('../classic-light.css'))}
export function loadAppearance(design = getDesign(), theme = getColorTheme()) {
  return Promise.all([
    design === 'editorial' ? skins.editorial() : Promise.resolve(),
    design === 'classic' && theme === 'light' ? skins.classic() : Promise.resolve(),
  ])
}
export async function setAppearance(design: Design, theme: ColorTheme, persist = true) {
  const request = ++revision
  await loadAppearance(design, theme)
  if (request !== revision) return

  const root = document.documentElement
  root.dataset.design = design
  root.dataset.theme = theme
  root.classList.toggle('dark', theme === 'dark')
  if (persist) try {
    localStorage.setItem('xyz:design', design)
    localStorage.setItem('xyz:color-theme', theme)
  } catch { /* Controls remain usable when storage is unavailable. */ }
  window.dispatchEvent(new Event(event))
}
export function useAppearance() {
  const design = useSyncExternalStore(subscribe, getDesign)
  const theme = useSyncExternalStore(subscribe, getColorTheme)
  return {design, theme}
}
