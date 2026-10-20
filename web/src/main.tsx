import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/Toast'
import PageErrorBoundary from './components/PageErrorBoundary'
import './index.css'
import { registerPublicCache } from './lib/publicCache'

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
mount()
registerPublicCache()
