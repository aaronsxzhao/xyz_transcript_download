import { getStoredUser } from './auth'

export function getAccountId(): string {
  return getStoredUser()?.id || 'local'
}

export function getPreference(key: string): string | null {
  const scoped = localStorage.getItem(`xyz_pref:${getAccountId()}:${key}`)
  // Existing single-user installations retain their local preferences.
  return scoped ?? (getAccountId() === 'local' ? localStorage.getItem(key) : null)
}

export function setPreference(key: string, value: string): void {
  localStorage.setItem(`xyz_pref:${getAccountId()}:${key}`, value)
}
