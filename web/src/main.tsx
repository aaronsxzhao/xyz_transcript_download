import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/Toast'
import PageErrorBoundary from './components/PageErrorBoundary'
import './index.css'
import {loadAppearance, setAppearance} from './lib/theme'
import './appearance.css'
import { registerPublicCache } from './lib/publicCache'
import {recoverPageImport} from './lib/chunkRecovery'

// Optional tools have their own inline boundaries. Only a replaced route
// controller should refresh the document automatically.
window.addEventListener('vite:preloadError',event=>{
  const message=String((event as Event & {payload?:unknown}).payload||'')
  if(/\/(?:Settings|Dashboard|Podcasts|Episodes|Viewer|Videos|VideoViewer)-[^/]+\.js/.test(message)) recoverPageImport(event)
})

if (new URLSearchParams(window.location.hash.slice(1)).get('type') === 'recovery') {
  window.history.replaceState(null, '', '/reset-password' + window.location.hash)
}

const startupURL = new URL(location.href)
if (startupURL.searchParams.has('__xyz_boot')) {
  startupURL.searchParams.delete('__xyz_boot')
  history.replaceState(null, '', startupURL.pathname + startupURL.search + startupURL.hash)
}

function mount() { ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PageErrorBoundary>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
    </PageErrorBoundary>
  </React.StrictMode>,
) }

// Production styles arrive in the document. No stylesheet event can strand
// navigation, page controllers or their data reads behind a permanent wait.
// Optional skins are loaded only when selected, before rendering that appearance.
// A failed optional asset must not strand the application at startup.
loadAppearance().catch(() => setAppearance('classic', 'dark', false)).then(mount)
registerPublicCache()
