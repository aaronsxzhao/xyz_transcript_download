import { ReactNode, useEffect } from 'react'
import { Menu } from 'lucide-react'
import Sidebar from './Sidebar'
import ProcessingPanel from './ProcessingPanel'
import { connectWebSocket, disconnectWebSocket } from '../lib/websocket'
import { useStore } from '../lib/store'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { sidebarOpen, toggleSidebar } = useStore()
  
  useEffect(() => {
    connectWebSocket()
    return () => disconnectWebSocket()
  }, [])
  
  return (
    <div className="flex h-screen bg-dark-bg">
      <Sidebar />
      
      {/* Mobile overlay when sidebar is open */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-30 md:hidden"
          onClick={toggleSidebar}
        />
      )}
      
      <main className={`flex-1 overflow-auto transition-all ${sidebarOpen ? 'md:ml-64' : 'md:ml-16'}`}>
        {/* Mobile header with menu button */}
        <div className="sticky top-0 z-20 flex items-center gap-4 p-4 bg-dark-bg border-b border-dark-border md:hidden">
          <button
            onClick={toggleSidebar}
            className="p-2 rounded-lg hover:bg-dark-hover transition-colors"
          >
            <Menu size={24} />
          </button>
          <span className="font-semibold text-lg">Podcast Tool</span>
        </div>
        
        <div className="p-4 md:p-6">
          {children}
        </div>
      </main>
      
      {/* Processing panel - shows active jobs */}
      <ProcessingPanel />
    </div>
  )
}
