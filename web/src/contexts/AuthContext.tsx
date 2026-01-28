/**
 * Authentication context for managing user state
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
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
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)

  // Check auth status on mount
  useEffect(() => {
    async function checkAuth() {
      try {
        // First check if auth is enabled
        const config = await getAuthConfig()
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
            setUser(currentUser)
          }
        }
      } catch (error) {
        console.error('Auth check failed:', error)
        setUser(null)
      } finally {
        setLoading(false)
      }
    }

    checkAuth()
  }, [])

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
    }
    // If no access token, email confirmation may be required
  }

  const signOut = async () => {
    await authSignOut()
    setUser(null)
  }

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
