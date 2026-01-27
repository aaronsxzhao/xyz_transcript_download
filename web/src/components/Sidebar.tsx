import { Link, useLocation } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Radio, 
  Settings, 
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useStore } from '../lib/store'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/podcasts', icon: Radio, label: 'Podcasts' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const location = useLocation()
  const { sidebarOpen, toggleSidebar } = useStore()
  
  return (
    <aside className={`fixed left-0 top-0 h-full bg-dark-surface border-r border-dark-border transition-all ${sidebarOpen ? 'w-64' : 'w-16'}`}>
      {/* Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-dark-border">
        {sidebarOpen && (
          <div className="flex items-center gap-2">
            <Radio className="w-6 h-6 text-indigo-500" />
            <span className="font-semibold text-lg">Podcast Tool</span>
          </div>
        )}
        <button 
          onClick={toggleSidebar}
          className="p-2 rounded-lg hover:bg-dark-hover transition-colors"
        >
          {sidebarOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
        </button>
      </div>
      
      {/* Navigation */}
      <nav className="p-4 space-y-2">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          const Icon = item.icon
          
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                isActive 
                  ? 'bg-indigo-600 text-white' 
                  : 'text-gray-400 hover:bg-dark-hover hover:text-white'
              }`}
            >
              <Icon size={20} />
              {sidebarOpen && <span>{item.label}</span>}
            </Link>
          )
        })}
      </nav>
      
      {/* Footer */}
      {sidebarOpen && (
        <div className="absolute bottom-4 left-4 right-4">
          <div className="p-3 bg-dark-hover rounded-lg text-xs text-gray-500">
            <p>Podcast Transcript Tool</p>
            <p>v1.0.0</p>
          </div>
        </div>
      )}
    </aside>
  )
}
