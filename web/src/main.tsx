import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/Toast'
import PageErrorBoundary from './components/PageErrorBoundary'
import { recoverPageImport } from './lib/chunkRecovery'
import './index.css'

window.addEventListener('vite:preloadError', recoverPageImport)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PageErrorBoundary>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
    </PageErrorBoundary>
  </React.StrictMode>,
)
