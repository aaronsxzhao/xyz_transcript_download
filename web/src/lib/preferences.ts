import { getStoredUser } from './auth'

export function getAccountId(): string {
  return getStoredUser()?.id || 'local'
}

export function getPreference(key: string): string | null {
  try {
    const scoped = localStorage.getItem(`xyz_pref:${getAccountId()}:${key}`)
    // Existing single-user installations retain their local preferences.
    return scoped ?? (getAccountId() === 'local' ? localStorage.getItem(key) : null)
  } catch {
    return null
  }
}

export function setPreference(key: string, value: string): void {
  try {
    localStorage.setItem(`xyz_pref:${getAccountId()}:${key}`, value)
  } catch {
    // Reading controls remain usable when the browser blocks persistence.
  }
}
