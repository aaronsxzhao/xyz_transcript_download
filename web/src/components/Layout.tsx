import { Outlet } from 'react-router-dom'
import TopNav from './TopNav'
import ProcessingPanel from './ProcessingPanel'
import { useAuth } from '../contexts/AuthContext'

export default function Layout() {
  const { user } = useAuth()
  return (
    <div className="flex flex-col h-screen bg-dark-bg overflow-hidden">
      <TopNav />

      <main className="flex-1 min-h-0 overflow-auto">
        <div className="p-4 md:p-6">
          <Outlet key={user?.id} />
        </div>
      </main>

      <ProcessingPanel />
    </div>
  )
}
