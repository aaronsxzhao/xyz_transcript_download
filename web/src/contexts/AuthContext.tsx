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
  isAuthenticated,
  getStoredUser,
  getAuthGeneration,
  watchStoredSession,
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
  // Restore this browser's existing UI immediately. This is not authorization:
  // every API request still carries a token verified by the backend.
  const [restored] = useState(() => {
    const stored = isAuthenticated() ? getStoredUser() : null
    return stored?.authenticated && typeof stored.id === 'string' ? stored : null
  })
  const [user, setUser] = useState<AuthUser | null>(restored)
  const [loading, setLoading] = useState(!restored)
  const [authEnabled, setAuthEnabled] = useState(!!restored)
  const [authError, setAuthError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const changed = () => {
      disconnectWebSocket()
      useStore.getState().reset()
      clearCache()
      setUser(isAuthenticated() ? getStoredUser() : null)
      setAuthError('')
    }
    window.addEventListener('xyz:session-changed', changed)
    const stop = watchStoredSession()
    return () => { stop(); window.removeEventListener('xyz:session-changed', changed) }
  }, [])

  useEffect(() => {
    if (!loading && user) connectWebSocket()
    return disconnectWebSocket
  }, [user?.id, loading])

  // Check auth status on mount
  useEffect(() => {
    let active = true
    async function checkAuth() {
      const owner = getAuthGeneration()
      if (!restored) setLoading(true)
      setAuthError('')
      try {
        // First check if auth is enabled
        const [config, currentUser] = await Promise.all([
          getAuthConfig(),
          isAuthenticated() ? getCurrentUser() : Promise.resolve(null),
        ])
        if (!active || owner !== getAuthGeneration()) return
        setAuthEnabled(config.supabase_enabled)

        if (!config.supabase_enabled) {
          // Auth not enabled, use local mode
          setUser({ id: 'local', email: 'local@localhost', authenticated: true })
          setLoading(false)
          return
        }

        setUser(currentUser)
      } catch (error) {
        if (!active || owner !== getAuthGeneration()) return
        console.error('Auth check failed:', error)
        if (!restored) setUser(null)
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

  if (authError && !user) return (
    <div className="min-h-screen bg-dark-bg text-gray-200 flex flex-col items-center justify-center gap-4 p-6" role="alert">
      <p>{authError}</p>
      <button className="px-4 py-2 bg-indigo-600 rounded-lg" onClick={() => setAttempt(value => value + 1)}>Retry connection</button>
    </div>
  )

  return (
    <AuthContext.Provider value={{ user, loading, authEnabled, signIn, signUp, signOut }}>
      {authError && <div role="alert" className="bg-dark-surface text-gray-300 px-4 py-2 text-sm">
        {authError} <button className="underline ml-2" onClick={() => setAttempt(value => value + 1)}>Retry connection</button>
      </div>}
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
