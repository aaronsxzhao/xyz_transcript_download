export function platformLabel(platform:string|undefined,fallback='Podcast'):string {
  return ({xiaoyuzhou:'小宇宙',apple:'Apple Podcasts',spotify:'Spotify',local:'Local Uploads',youtube:'YouTube',bilibili:'Bilibili',douyin:'抖音',kuaishou:'快手',twitter:'X / Twitter',substack:'Substack',web:'Web'} as Record<string,string>)[platform||'']||platform||fallback
}
