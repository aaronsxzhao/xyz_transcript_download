import { expect, it } from 'vitest'
import { videoFailureHint } from '../src/lib/videoFailure'

it.each([
  ['GEO_RESTRICTED', 'HTTP Error 403: sign in', 'region'],
  ['RATE_LIMITED', 'Sign in to confirm you are not a bot', 'Too many requests'],
  ['VIDEO_PRIVATE', 'Sign in to view', 'private'],
  ['COPYRIGHT_BLOCKED', 'Video unavailable', 'copyright'],
  ['VIDEO_UNAVAILABLE', 'Region music', 'unavailable'],
  ['AGE_RESTRICTED', 'Sign in', 'age verification'],
])('uses the classified %s reason before generic provider wording', (error, message, expected) => {
  expect(videoFailureHint({ error, message })).toContain(expected)
})

it('classifies historical overlapping errors without sending every user to login', () => {
  expect(videoFailureHint({ message: 'HTTP 429: Sign in to confirm you are not a bot' })).toContain('Too many requests')
  expect(videoFailureHint({ message: 'HTTP 403: This video is not available in your country' })).toContain('region')
  expect(videoFailureHint({ message: 'Private video. Sign in to view' })).toContain('private')
  expect(videoFailureHint({ message: 'Video unavailable due to copyright' })).toContain('copyright')
})

it('retains actual source account guidance without guessing copyright or age restrictions', () => {
  expect(videoFailureHint({ error: 'LOGIN_REQUIRED' })).toContain('platform account')
  expect(videoFailureHint({ message: 'Unable to download webpage: network blocked' })).not.toContain('copyright')
  expect(videoFailureHint({ message: 'Failed to download page' })).not.toContain('age verification')
  expect(videoFailureHint({})).not.toContain('account')
})
