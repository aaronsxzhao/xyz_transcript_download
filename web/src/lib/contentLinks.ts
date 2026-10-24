const hosts:Record<string,RegExp>={
  twitter:/^(?:(?:www|mobile)\.)?(?:x|twitter)\.com$|^t\.co$/,
  substack:/(^|\.)substack\.com$/,
  bilibili:/(^|\.)bilibili\.com$|^b23\.tv$/,
  youtube:/(^|\.)youtube\.com$|^youtu\.be$/,
  douyin:/(^|\.)(douyin|tiktok)\.com$/,
  kuaishou:/(^|\.)(kuaishou|kwai)\.com$/,
}
/** Import origin is independent of the public RSS used to fetch its audio. */
export function detectPodcastPlatform(raw:string):string {
  try {
    const url=new URL(raw)
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password||!['','80','443'].includes(url.port))return ''
    return ({'xiaoyuzhoufm.com':'xiaoyuzhou','www.xiaoyuzhoufm.com':'xiaoyuzhou','podcasts.apple.com':'apple','itunes.apple.com':'apple','open.spotify.com':'spotify'} as Record<string,string>)[url.hostname.toLowerCase()]||''
  }catch{return ''}
}
/** Detect links by hostname; pasted page text must not spoof a platform. */
export function detectContentPlatform(raw:string):string {
  try {
    const url=new URL(raw.match(/https?:\/\/[^\s]+/)?.[0]||raw)
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password)return ''
    const host=url.hostname.toLowerCase()
    for(const platform in hosts)if(hosts[platform].test(host))return platform
    if(/^\/(?:embed\/)?p\/[^/]+\/?$/.test(url.pathname))return 'substack'
  }catch{}
  return ''
}
