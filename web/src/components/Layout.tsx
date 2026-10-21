import { Outlet } from 'react-router-dom'
import { Suspense } from 'react'
import { Loader2 } from 'lucide-react'
import TopNav from './TopNav'
import ProcessingPanel from './ProcessingPanel'
import { useAuth } from '../contexts/AuthContext'

export default function Layout() {
  const { user } = useAuth()
  return (
    <div className="app-shell flex flex-col h-screen bg-dark-bg overflow-hidden">
      <TopNav />

      <main className="flex-1 min-h-0 overflow-auto">
        <div className="page-frame">
          <Suspense fallback={<div className="py-12 flex justify-center"><Loader2 className="animate-spin text-indigo-500" aria-label="Loading page" /></div>}>
            <Outlet key={user?.id} />
          </Suspense>
        </div>
      </main>

      <ProcessingPanel />
    </div>
  )
}
