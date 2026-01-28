import { ReactNode, useEffect } from 'react'
import Sidebar from './Sidebar'
import ProcessingPanel from './ProcessingPanel'
import { connectWebSocket, disconnectWebSocket } from '../lib/websocket'
import { useStore } from '../lib/store'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { sidebarOpen } = useStore()
  
  useEffect(() => {
    connectWebSocket()
    return () => disconnectWebSocket()
  }, [])
  
  return (
    <div className="flex h-screen bg-dark-bg">
      <Sidebar />
      
      <main className={`flex-1 overflow-auto transition-all ${sidebarOpen ? 'ml-64' : 'ml-16'}`}>
        <div className="p-6">
          {children}
        </div>
      </main>
      
      {/* Processing panel - shows active jobs */}
      <ProcessingPanel />
    </div>
  )
}
