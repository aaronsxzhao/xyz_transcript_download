/** Classified reasons take precedence over overlapping words in provider errors. */
export function videoFailureHint(task: { error?: string; message?: string }): string {
  const code = (task.error || '').trim()
  return (/^[A-Z_]+$/.test(code) ? hint(code) : '') || hint(`${code} ${task.message || ''}`)
    || 'Request failed. Check the source and error details.'
}

function hint(text: string): string {
  const message = text.toLowerCase()
  if (/rate.limit|too many requests|\b429\b/.test(message))
    return 'Too many requests. Wait a few minutes before retrying.'
  if (/copyright/.test(message))
    return 'Blocked due to copyright.'
  if (/geo.restrict|geo.block|not available in your (country|region)/.test(message))
    return 'Unavailable in the server region. Check the source.'
  if (/video_private|private video|video is private/.test(message))
    return 'This video is private. Check source access.'
  if (/age.restrict|confirm your age|age.verif/.test(message))
    return 'Requires age verification in your platform account.'
  if (/login|cookie|\b403\b|sign.in|\b412\b/.test(message))
    return 'Sign-in required. Check your platform account in Settings.'
  if (/unavailable|not found|\b404\b|removed/.test(message))
    return 'Video unavailable. Check the source.'
  if (/timeout|timed out/.test(message))
    return 'Request timed out. Retry later.'
  if (/unsupported/.test(message))
    return 'Unsupported URL.'
  return ''
}
