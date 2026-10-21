/** Public provider covers use our persistent cache; private files keep their signed path. */
export function artworkUrl(raw: string): string {
  if (/^\/data\/(screenshots|thumbnails)\/[a-zA-Z0-9_.-]+\.(jpg|jpeg|png|webp)(\?|$)/.test(raw)) {
    return raw + (raw.includes('?') ? '&' : '?') + 'preview=true'
  }
  if (!/^https?:\/\//i.test(raw)) return ''
  return `/api/image-proxy?url=${encodeURIComponent(raw)}&v=2`
}
