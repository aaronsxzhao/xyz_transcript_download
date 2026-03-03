import { Outlet } from 'react-router-dom'
import TopNav from './TopNav'
import ProcessingPanel from './ProcessingPanel'

export default function Layout() {
  return (
    <div className="flex flex-col h-screen bg-dark-bg overflow-hidden">
      <TopNav />

      <main className="flex-1 min-h-0 overflow-auto">
        <div className="p-4 md:p-6">
          <Outlet />
        </div>
      </main>

      <ProcessingPanel />
    </div>
  )
}
