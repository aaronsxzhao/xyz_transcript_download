import { ReactNode, useEffect } from 'react'
import Sidebar from './Sidebar'
import { connectWebSocket, disconnectWebSocket } from '../lib/websocket'
import { useStore } from '../lib/store'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { sidebarOpen, wsConnected } = useStore()
  
  useEffect(() => {
    connectWebSocket()
    return () => disconnectWebSocket()
  }, [])
  
  return (
    <div className="flex h-screen bg-dark-bg">
      <Sidebar />
      
      <main className={`flex-1 overflow-auto transition-all ${sidebarOpen ? 'ml-64' : 'ml-16'}`}>
        <div className="p-6">
          {/* Connection status indicator */}
          <div className="fixed top-4 right-4 flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-500">{wsConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
          
          {children}
        </div>
      </main>
    </div>
  )
}
