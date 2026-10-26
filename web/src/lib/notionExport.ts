import {authFetch,parseApiResponseAsJson} from './api'
import {requestWithDeadline} from './requestDeadline'
import {getAuthGeneration} from './auth'
import {getPreference} from './preferences'
function assertOwner(generation:number){if(generation!==getAuthGeneration())throw new DOMException('Account changed','AbortError')}
import type {VideoTask} from './api'
export function buildNotionExportMarkdown(task: VideoTask, content: string, selectedVersion = ''): string {
  const lines: string[] = []
  const title = task.title?.trim() || 'Untitled Video Note'

  lines.push(`# ${title}`)
  lines.push('')

  const metadata: string[] = []
  if (task.platform) metadata.push(`- Platform: ${task.platform}`)
  if (task.channel) metadata.push(`- Channel: ${task.channel}`)
  const style = selectedVersion ? task.versions?.find(version=>version.id===selectedVersion)?.style : task.style
  if (style) metadata.push(`- Style: ${style}`)
  if (task.duration > 0) {
    const m = Math.floor(task.duration / 60)
    const s = Math.floor(task.duration % 60)
    metadata.push(`- Duration: ${m}:${s.toString().padStart(2, '0')}`)
  }
  if (task.url) metadata.push(`- Source: ${task.url}`)

  if (metadata.length > 0) {
    lines.push('## Details')
    lines.push('')
    lines.push(...metadata)
    lines.push('')
  }

  if (content.trim()) {
    const body = content.replace(/^[\r\n]+|[\r\n]+$/g, '')
    const firstLine = body.split(/\r?\n/, 1)[0]
    // The saved note usually already carries the task title. Keep one page
    // title while retaining any different source heading and all body bytes.
    const text = /^ {0,3}# /.test(firstLine) && firstLine.trim() === `# ${title}` ? body.slice(firstLine.length).replace(/^(?:[ \t]*\r?\n)+/, '') : body
    if (text) lines.push(text)
    lines.push('')
  }

  return lines.join('\n')
}


export async function submitNotionExport(path: string, body: object): Promise<{ url: string; page_id: string; title: string }> {
  const generation=getAuthGeneration(),key=getPreference('notion_api_key') || ''
  return requestWithDeadline(async signal => {
    assertOwner(generation)
    const res = await authFetch(`/api/notion/${path}`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Notion-Key': key,
      },
      body: JSON.stringify(body),
    })
    const result = await parseApiResponseAsJson<{url:string;page_id:string;title:string}>(res, 'Export to Notion failed')
    assertOwner(generation)
    if (!result || typeof result.page_id !== 'string' || !result.page_id || typeof result.url !== 'string' || typeof result.title !== 'string')
      throw new Error('Notion returned an incomplete export confirmation. Check Notion before exporting again.')
    return result
  }, {timeout:120000,message:'Notion did not confirm the export in time. It may still be running.'})
}


export async function fetchNotionPages(query?:string):Promise<{pages:import('./api').NotionPage[]}> {
  const params=query ? `?query=${encodeURIComponent(query)}` : ''
  const res=await authFetch(`/api/notion/pages${params}`,{headers:{'X-Notion-Key':getPreference('notion_api_key') || ''}})
  return parseApiResponseAsJson(res,'Failed to fetch Notion pages')
}
