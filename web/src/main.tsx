import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/Toast'
import PageErrorBoundary from './components/PageErrorBoundary'
import { recoverPageImport } from './lib/chunkRecovery'
import './index.css'

if (new URLSearchParams(window.location.hash.slice(1)).get('type') === 'recovery') {
  window.history.replaceState(null, '', '/reset-password' + window.location.hash)
}

const startupURL = new URL(location.href)
if (startupURL.searchParams.has('__xyz_boot')) {
  startupURL.searchParams.delete('__xyz_boot')
  history.replaceState(null, '', startupURL.pathname + startupURL.search + startupURL.hash)
}

window.addEventListener('vite:preloadError', recoverPageImport)

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

// The public shell paints without waiting for the stylesheet or framework.
// Switch to the application only after its complete stylesheet is available.
const styles = Array.from(document.querySelectorAll<HTMLLinkElement>('link[data-app-style]'))
void Promise.all(styles.map(link => link.dataset.ready === 'true' || link.media === 'all' ? Promise.resolve() : new Promise<void>((resolve, reject) => {
  link.addEventListener('load', () => { link.media = 'all'; resolve() }, {once:true})
  link.addEventListener('error', () => reject(new Error('Stylesheet unavailable')), {once:true})
}))).then(mount).catch(() => {
  const message = document.getElementById('startup-status')
  if (message) message.textContent = 'The page styles could not load. Please retry loading.'
  const retry = document.getElementById('startup-retry')
  if (retry) retry.hidden = false
})
