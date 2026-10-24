/** Source restrictions belong to a task/platform, not the website session. */
export function taskSource(platform = '', url = '', episodeId = '', kind?: string) {
  const name = ({youtube:'YouTube',bilibili:'BiliBili',local:'Local upload',xiaoyuzhou:'Xiaoyuzhou',twitter:'X / Twitter',substack:'Substack'} as Record<string,string>)[platform] || (kind === 'podcast' ? 'Podcast' : 'Video')
  let id = '', original = ''
  try {
    const source = new URL(url)
    const host = source.hostname.toLowerCase()
    if (platform === 'youtube' && ['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(host)) {
      const candidate = host === 'youtu.be' ? source.pathname.slice(1) : source.searchParams.get('v') || source.pathname.match(/^\/(?:shorts|live|embed)\/([^/]+)/)?.[1] || ''
      if (/^[a-zA-Z0-9_-]{11}$/.test(candidate)) { id = candidate; original = `https://www.youtube.com/watch?v=${id}` }
    } else if (platform === 'twitter' && ['x.com','www.x.com','mobile.x.com','twitter.com','www.twitter.com','mobile.twitter.com','t.co'].includes(host)) {
      original=source.href
    } else if (platform === 'substack' && /^https?:$/.test(source.protocol) && !source.username && !source.password) {
      original=source.href
    } else if (platform === 'bilibili' && /(^|\.)bilibili\.com$/.test(host)) {
      id = source.pathname.match(/\/video\/(BV[a-zA-Z0-9]+|av\d+)/)?.[1] || ''
      if (id) original = `https://www.bilibili.com/video/${id}`
    }
  } catch { /* A missing/malformed URL still retains platform and task identity. */ }
  if (kind === 'podcast' && /^[a-f0-9]{24}$/i.test(episodeId)) original = `https://www.xiaoyuzhoufm.com/episode/${episodeId}`
  return { name, id, original }
}

export function taskFailure(message = '', platform = '') {
  const login = /^(?:BILIBILI_)?LOGIN_REQUIRED$|^COOKIES_REQUIRED$|^AGE_RESTRICTED$/i.test(message.trim())
  if (!login) return { message, retryAfterSignIn: false }
  const name = taskSource(platform).name
  if (platform === 'twitter' || platform === 'substack') return {
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
