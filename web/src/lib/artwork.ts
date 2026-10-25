/** Public provider covers use our persistent cache; private files keep their signed path. */
export function artworkUrl(raw: string): string {
  if(raw.startsWith('/api/article-image?')){const url=new URL(raw,'https://reader.invalid');url.searchParams.set('size','cover');return url.pathname+url.search}
  if (/^\/data\/(screenshots|thumbnails)\/[a-zA-Z0-9_.-]+\.(jpg|jpeg|png|webp)(\?|$)/.test(raw)) {
    return raw + (raw.includes('?') ? '&' : '?') + 'preview=true'
  }
  if (!/^https?:\/\//i.test(raw)) return ''
  return `/api/image-proxy?url=${encodeURIComponent(raw)}&v=2`
}
