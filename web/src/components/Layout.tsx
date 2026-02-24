import { ReactNode, useEffect } from 'react'
import TopNav from './TopNav'
import ProcessingPanel from './ProcessingPanel'
import { connectWebSocket, disconnectWebSocket } from '../lib/websocket'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  useEffect(() => {
    connectWebSocket()
    return () => disconnectWebSocket()
  }, [])

  return (
    <div className="flex flex-col h-screen bg-dark-bg overflow-hidden">
      <TopNav />

      <main className="flex-1 min-h-0 overflow-auto">
        <div className="p-4 md:p-6">
          {children}
        </div>
      </main>

      <ProcessingPanel />
    </div>
  )
}
