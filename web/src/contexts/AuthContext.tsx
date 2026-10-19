/**
 * Authentication context for managing user state
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { clearCache } from '../lib/cache'
import { useStore } from '../lib/store'
import { connectWebSocket, disconnectWebSocket } from '../lib/websocket'
import {
  AuthUser,
  getAuthConfig,
  getCurrentUser,
  signIn as authSignIn,
  signUp as authSignUp,
  signOut as authSignOut,
  getStoredUser,
  isAuthenticated,
} from '../lib/auth'

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  authEnabled: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<boolean>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authError, setAuthError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const changed = () => {
      disconnectWebSocket()
      useStore.getState().reset()
      clearCache()
      if (!isAuthenticated()) setUser(null)
    }
    window.addEventListener('xyz:session-changed', changed)
    return () => window.removeEventListener('xyz:session-changed', changed)
  }, [])

  useEffect(() => {
    if (!loading && user) connectWebSocket()
    return disconnectWebSocket
  }, [user?.id, loading])

  // Check auth status on mount
  useEffect(() => {
    let active = true
    async function checkAuth() {
      setLoading(true)
      setAuthError('')
      try {
        // First check if auth is enabled
        const config = await getAuthConfig()
        if (!active) return
        setAuthEnabled(config.supabase_enabled)

        if (!config.supabase_enabled) {
          // Auth not enabled, use local mode
          setUser({ id: 'local', email: 'local@localhost', authenticated: true })
          setLoading(false)
          return
        }

        // Check if we have stored tokens
        if (isAuthenticated()) {
          // Try to get current user
          const currentUser = await getCurrentUser()
          if (!active) return
          if (currentUser) {
            setUser(currentUser)
          } else {
            // Token expired or invalid
            setUser(null)
          }
        } else {
          // Check for stored user (for quick UI)
          const stored = getStoredUser()
          if (stored) {
            // Verify with server
            const currentUser = await getCurrentUser()
            if (active) setUser(currentUser)
          }
        }
      } catch (error) {
        if (!active) return
        console.error('Auth check failed:', error)
        setUser(null)
        setAuthError(error instanceof Error ? error.message : 'Cannot connect to the server')
      } finally {
        if (active) setLoading(false)
      }
    }

    checkAuth()
    return () => { active = false }
  }, [attempt])

  const signIn = async (email: string, password: string) => {
    const tokens = await authSignIn(email, password)
    setUser({
      id: tokens.user_id,
      email: tokens.email,
      authenticated: true,
    })
  }

  const signUp = async (email: string, password: string) => {
    const tokens = await authSignUp(email, password)
    if (tokens.access_token) {
      setUser({
        id: tokens.user_id,
        email: tokens.email,
        authenticated: true,
      })
      return true
    }
    return false
  }

  const signOut = async () => {
    setUser(null)
    await authSignOut()
  }

  if (authError) return (
    <div className="min-h-screen bg-dark-bg text-gray-200 flex flex-col items-center justify-center gap-4 p-6" role="alert">
      <p>{authError}</p>
      <button className="px-4 py-2 bg-indigo-600 rounded-lg" onClick={() => setAttempt(value => value + 1)}>Retry connection</button>
    </div>
  )

  return (
    <AuthContext.Provider value={{ user, loading, authEnabled, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
