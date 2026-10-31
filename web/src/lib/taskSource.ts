/** Source restrictions belong to a task/platform, not the website session. */
import { detectPodcastPlatform } from './contentLinks'
import { platformLabel } from './platformLabels'
export function taskSource(platform = '', url = '', episodeId = '', kind?: string) {
  platform = platform || detectPodcastPlatform(url)
  const rss = url.startsWith('apple://')
  const local = platform === 'local' || url.startsWith('local://')
  const name = rss ? 'Public RSS' : local ? 'Local upload' : platformLabel(platform,kind === 'podcast' ? 'Podcast' : 'Video')
  let id = '', original = ''
  try {
    const source = new URL(url)
    if(source.username || source.password)throw new Error('Unsupported source credentials')
    const host = source.hostname.toLowerCase()
    if (platform === 'spotify' && host === 'open.spotify.com' && source.protocol==='https:') {
      id=source.pathname.match(/^\/(?:intl-[a-zA-Z-]+\/)?(?:embed\/)?episode\/([a-zA-Z0-9]{22})\/?$/)?.[1]||''
      if(id)original=`https://open.spotify.com/episode/${id}`
    } else if (platform === 'apple' && ['podcasts.apple.com','itunes.apple.com'].includes(host) && /^https?:$/.test(source.protocol)) {
      original=source.origin+source.pathname
      const episode=source.searchParams.get('i')
      if(episode && /^\d+$/.test(episode))original+='?i='+episode
    } else if (platform === 'youtube' && ['youtube.com','www.youtube.com','m.youtube.com','youtu.be','youtube-nocookie.com','www.youtube-nocookie.com'].includes(host)) {
      const candidate = host === 'youtu.be' ? source.pathname.slice(1) : source.searchParams.get('v') || source.pathname.match(/^\/(?:shorts|live|embed)\/([^/]+)/)?.[1] || ''
      if (/^[a-zA-Z0-9_-]{11}$/.test(candidate)) { id = candidate; original = `https://www.youtube.com/watch?v=${id}` }
    } else if (platform === 'twitter' && ['x.com','www.x.com','mobile.x.com','twitter.com','www.twitter.com','mobile.twitter.com','t.co'].includes(host)) {
      original=source.href
    } else if (['substack','web'].includes(platform) && /^https?:$/.test(source.protocol) && !source.username && !source.password) {
      original=source.href
    } else if (platform === 'bilibili' && ['b23.tv','www.b23.tv'].includes(host) && /^https?:$/.test(source.protocol)) {
      original=source.origin+source.pathname
    } else if (platform === 'bilibili' && /(^|\.)bilibili\.com$/.test(host)) {
      id = source.pathname.match(/\/video\/(BV[a-zA-Z0-9]+|av\d+)/)?.[1] || ''
      if (id) {
        original = `https://www.bilibili.com/video/${id}`
        const page = source.searchParams.get('p') || ''
        if (/^[1-9]\d{0,3}$/.test(page)) original += `?p=${page}`
      }
    }
  } catch { /* A missing/malformed URL still retains platform and task identity. */ }
  if (kind === 'podcast' && (!url || platform === 'xiaoyuzhou') && !rss && !local && /^[a-f0-9]{24}$/i.test(episodeId)) original = `https://www.xiaoyuzhoufm.com/episode/${episodeId}`
  return { name, id, original }
}

export function taskFailure(message = '', platform = '') {
  const login = /^(?:BILIBILI_)?LOGIN_REQUIRED$|^COOKIES_REQUIRED$|^AGE_RESTRICTED$/i.test(message.trim())
  if (!login) return { message, retryAfterSignIn: false }
  const name = taskSource(platform).name
  if (['twitter','substack','spotify','web'].includes(platform)) return {
    message: `${name} did not allow public access when this task ran. Open the original link to check access. Private or subscription-only content cannot be imported through the public link.`,
    retryAfterSignIn: false,
  }
  return {
    message: platform === 'youtube'
      ? 'YouTube requested sign-in or anti-bot verification when this task ran. Check YouTube in Settings, then retry.'
      : `${name} requested source account access when this task ran. Check its account in Settings, then retry.`,
    retryAfterSignIn: true,
  }
}
