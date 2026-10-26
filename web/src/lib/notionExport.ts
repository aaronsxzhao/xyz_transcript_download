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

