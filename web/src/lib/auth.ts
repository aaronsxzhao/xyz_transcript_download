/**
 * Authentication utilities for Supabase
 */

const API_BASE = '/api/auth'

export interface AuthConfig {
  supabase_enabled: boolean
  supabase_url: string | null
}

export interface AuthUser {
  id: string
  email: string
  authenticated: boolean
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  user_id: string
  email: string
}

// Token storage keys
const ACCESS_TOKEN_KEY = 'xyz_access_token'
const REFRESH_TOKEN_KEY = 'xyz_refresh_token'
const USER_KEY = 'xyz_user'

/**
 * Get the authentication configuration from the server
 */
export async function getAuthConfig(): Promise<AuthConfig> {
  const res = await fetch(`${API_BASE}/config`)
  if (!res.ok) {
    return { supabase_enabled: false, supabase_url: null }
  }
  return res.json()
}

/**
 * Sign up a new user
 */
export async function signUp(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${API_BASE}/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to sign up')
  }
  
  const tokens = await res.json()
  
  // Store tokens
  if (tokens.access_token) {
    saveTokens(tokens)
  }
  
  return tokens
}

/**
 * Sign in an existing user
 */
export async function signIn(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${API_BASE}/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Invalid email or password')
  }
  
  const tokens = await res.json()
  
  // Store tokens
  saveTokens(tokens)
  
  return tokens
}

/**
 * Sign out the current user
 */
export async function signOut(): Promise<void> {
  const token = getAccessToken()
  
  try {
    await fetch(`${API_BASE}/signout`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
  } catch (e) {
    // Ignore errors
  }
  
  // Clear stored tokens
  clearTokens()
}

/**
 * Get the current user
 */
export async function getCurrentUser(): Promise<AuthUser | null> {
  const token = getAccessToken()
  
  if (!token) {
    return null
  }
  
  const res = await fetch(`${API_BASE}/me`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  })
  
  if (!res.ok) {
    return null
  }
  
  const user = await res.json()
  
  if (!user.authenticated) {
    return null
  }
  
  return user
}

/**
 * Refresh the access token
 */
export async function refreshToken(): Promise<AuthTokens | null> {
  const refresh = getRefreshToken()
  
  if (!refresh) {
    return null
  }
  
  const res = await fetch(`${API_BASE}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  
  if (!res.ok) {
    clearTokens()
    return null
  }
  
  const tokens = await res.json()
  saveTokens(tokens)
  
  return tokens
}

/**
 * Get the stored access token
 */
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

/**
 * Get the stored refresh token
 */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

/**
 * Get the stored user
 */
export function getStoredUser(): AuthUser | null {
  const stored = localStorage.getItem(USER_KEY)
  if (!stored) return null
  try {
    return JSON.parse(stored)
  } catch {
    return null
  }
}

/**
 * Save tokens to localStorage
 */
function saveTokens(tokens: AuthTokens): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  localStorage.setItem(USER_KEY, JSON.stringify({
    id: tokens.user_id,
    email: tokens.email,
    authenticated: true,
  }))
}

/**
 * Clear all stored tokens
 */
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getAccessToken()
}
