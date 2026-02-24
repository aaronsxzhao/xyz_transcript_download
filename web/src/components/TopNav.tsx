import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Radio,
  Video,
  Settings,
  LogOut,
  User,
  Menu,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/podcasts', icon: Radio, label: 'Podcasts' },
  { path: '/videos', icon: Video, label: 'Videos' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

export default function TopNav() {
  const location = useLocation()
  const { user, authEnabled, signOut } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleSignOut = async () => {
    await signOut()
  }

  return (
    <header className="sticky top-0 z-40 bg-dark-surface border-b border-dark-border">
      <div className="flex items-center justify-between h-12 px-4">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 flex-shrink-0">
          <Radio className="w-5 h-5 text-indigo-500" />
          <span className="font-semibold text-sm text-white hidden sm:inline">Podcast & Video Tool</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)
            const Icon = item.icon

            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-dark-hover hover:text-white'
                }`}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Right side: user + mobile toggle */}
        <div className="flex items-center gap-2">
          {authEnabled && user && (
            <div className="hidden sm:flex items-center gap-2">
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <User size={14} />
                <span className="max-w-[120px] truncate">{user.email}</span>
              </div>
              <button
                onClick={handleSignOut}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-hover rounded-lg transition-colors"
                title="Sign Out"
              >
                <LogOut size={14} />
              </button>
            </div>
          )}

          {/* Mobile menu button */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="p-1.5 rounded-lg hover:bg-dark-hover transition-colors md:hidden"
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <div className="md:hidden border-t border-dark-border bg-dark-surface p-2 space-y-1">
          {navItems.map((item) => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)
            const Icon = item.icon

            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-dark-hover hover:text-white'
                }`}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            )
          })}

          {authEnabled && user && (
            <button
              onClick={handleSignOut}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-dark-hover hover:text-white transition-colors"
            >
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          )}
        </div>
      )}
    </header>
  )
}
