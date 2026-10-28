// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { getPreference, setPreference } from '../src/lib/preferences'

vi.mock('../src/lib/auth', () => ({ getStoredUser: () => ({ id: 'reader' }) }))
afterEach(() => vi.restoreAllMocks())

it('keeps reading controls usable when browser storage is blocked', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
  expect(getPreference('reader_width')).toBeNull()
  expect(() => setPreference('reader_width', 'wide')).not.toThrow()
})

it('stores preferences under the active account', () => {
  const save=vi.spyOn(Storage.prototype, 'setItem')
  setPreference('reader_width', 'wide')
  expect(save).toHaveBeenCalledWith('xyz_pref:reader:reader_width', 'wide')
})
