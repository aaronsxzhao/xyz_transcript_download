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
const REMEMBER_ME_KEY = 'xyz_remember_me'
let generation = 0
let refreshInFlight: Promise<AuthTokens | null> | null = null
let configInFlight: Promise<AuthConfig> | null = null

export function getAuthGeneration(): number { return generation }

function sessionChanged(): void {
  generation += 1
  window.dispatchEvent(new Event('xyz:session-changed'))
}

/**
 * Get the appropriate storage based on "Remember Me" setting
 */
function getStorage(): Storage {
  const rememberMe = localStorage.getItem(REMEMBER_ME_KEY) === 'true'
  return rememberMe ? localStorage : sessionStorage
}

/**
 * Set the "Remember Me" preference
 */
export function setRememberMe(remember: boolean): void {
  if (remember) {
    localStorage.setItem(REMEMBER_ME_KEY, 'true')
  } else {
    localStorage.removeItem(REMEMBER_ME_KEY)
  }
}

/**
 * Get the "Remember Me" preference
 */
export function getRememberMe(): boolean {
  return localStorage.getItem(REMEMBER_ME_KEY) === 'true'
}

/**
 * Get the authentication configuration from the server
 */
export function getAuthConfig(): Promise<AuthConfig> {
  const embedded = document.getElementById('xyz-auth-config')?.textContent
  if (embedded) {
    try {
      const config = JSON.parse(embedded)
      if (typeof config.supabase_enabled === 'boolean' &&
          (config.supabase_url === null || typeof config.supabase_url === 'string')) return Promise.resolve(config)
    } catch { /* Development/older HTML falls back to the same-origin API. */ }
  }
  if (configInFlight) return configInFlight
  const request = fetch(`${API_BASE}/config`).then(res => {
    if (!res.ok) throw new Error('Cannot check the server connection. Please retry.')
    return res.json() as Promise<AuthConfig>
  }).finally(() => { if (configInFlight === request) configInFlight = null })
  configInFlight = request
  return request
}

/** Expiry is a scheduling hint only; the server still verifies every request. */
export function accessTokenNeedsRefresh(token = getAccessToken()): boolean {
  if (!token) return false
  try {
    const encoded = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(atob(encoded))
    return typeof payload.exp === 'number' && payload.exp <= Date.now() / 1000 + 30
  } catch { return false }
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
  clearTokens()
  
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
  
}

/**
 * Get the current user
 */
export async function getCurrentUser(): Promise<AuthUser | null> {
  const fetchUser = async (token: string): Promise<AuthUser | null> => {
    const res = await fetch(`${API_BASE}/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })

    if (res.status === 401) {
      return null
    }
    if (!res.ok) throw new Error('Cannot verify your session. Please retry.')

    const user = await res.json()
    if (!user.authenticated) {
      return null
    }
    return user
  }

  let token = getAccessToken()
  if (!token) {
    return null
  }
  if (accessTokenNeedsRefresh(token) && getRefreshToken()) {
    token = (await refreshToken())?.access_token || null
    if (!token) return null
  }

  const currentUser = await fetchUser(token)
  if (currentUser) {
    return currentUser
  }

  const refreshed = await refreshToken()
  if (!refreshed?.access_token) {
    return null
  }

  return fetchUser(refreshed.access_token)
}

/**
 * Refresh the access token
 */
export async function refreshToken(): Promise<AuthTokens | null> {
  if (refreshInFlight) return refreshInFlight
  const request = performRefresh()
  refreshInFlight = request
  try { return await request } finally {
    if (refreshInFlight === request) refreshInFlight = null
  }
}

async function performRefresh(): Promise<AuthTokens | null> {
  const startedGeneration = generation
  const refresh = getRefreshToken()
  
  if (!refresh) {
    if (getAccessToken()) clearTokens()
    return null
  }
  
  const res = await fetch(`${API_BASE}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  })
  
  if (startedGeneration !== generation || refresh !== getRefreshToken()) return null
  if (res.status === 401 || res.status === 400) {
    clearTokens()
    return null
  }
  if (!res.ok) throw new Error('Cannot refresh your session. Please retry.')
  
  const tokens = await res.json()
  if (startedGeneration !== generation || refresh !== getRefreshToken()) return null
  saveTokens(tokens)
  
  return tokens
}

/**
 * Get the stored access token
 */
export function getAccessToken(): string | null {
  // Check both storages (for migration and flexibility)
  return localStorage.getItem(ACCESS_TOKEN_KEY) || sessionStorage.getItem(ACCESS_TOKEN_KEY)
}

/**
 * Get the stored refresh token
 */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY) || sessionStorage.getItem(REFRESH_TOKEN_KEY)
}

/**
 * Get the stored user
 */
export function getStoredUser(): AuthUser | null {
  const stored = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY)
  if (!stored) return null
  try {
    return JSON.parse(stored)
  } catch {
    return null
  }
}

/**
 * Save tokens to storage based on "Remember Me" setting
 */
function saveTokens(tokens: AuthTokens): void {
  const previousOwner = getStoredUser()?.id
  const storage = getStorage()
  const otherStorage = storage === localStorage ? sessionStorage : localStorage

  // Remove any prior session from the non-selected storage so a past
  // "remember me" choice cannot override the current login preference.
  otherStorage.removeItem(ACCESS_TOKEN_KEY)
  otherStorage.removeItem(REFRESH_TOKEN_KEY)
  otherStorage.removeItem(USER_KEY)

  storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
  storage.setItem(USER_KEY, JSON.stringify({
    id: tokens.user_id,
    email: tokens.email,
    authenticated: true,
  }))
  if (previousOwner !== tokens.user_id) sessionChanged()
}

/**
 * Clear all stored tokens from both storages
 */
export function clearTokens(): void {
  // Clear from both storages
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
  refreshInFlight = null
  sessionChanged()
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getAccessToken()
}
