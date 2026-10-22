import type { KeyPoint, Summary } from './api'

/** CommonMark treats **中文。**后文 as literal asterisks. Move only the
 * closing punctuation outside emphasis, leaving text and code unchanged. */
export function normalizeSummaryMarkdown(markdown: string): string {
  return markdown.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).map((part, index) => index % 2 ? part : part.replace(/(?<!\\)\*\*(?=\S)([^*\n]+?)([，。；：！？、,.!?;:]+)\*\*(?=[\p{L}\p{N}])/gu, '**$1**$2')).join('')
}

/** New notes keep their labelled introduction in the existing overview field.
 * Legacy prose is left intact; no guessed heading or inferred grouping.
 */
export function summaryIntroduction(overview: string) {
  const match = overview.match(/^\s*### 核心结论\s*\r?\n([\s\S]*?)^### 节目概览\s*\r?\n([\s\S]*)$/m)
  if (!match || overview.slice(0, match.index).trim()) return { conclusions: '', overview }
  return { conclusions: match[1].trim(), overview: match[2].trim() }
}

export function summaryChapters(summary?: Summary | null): [string, KeyPoint[]][] {
  if (!summary) return []
  const groups = new Map<string, KeyPoint[]>()
  for (const topic of summary.topics) groups.set(topic, [])
  for (const point of summary.key_points) {
    if (!groups.has(point.topic)) groups.set(point.topic, [])
    groups.get(point.topic)!.push(point)
  }
  return [...groups].filter(([, points]) => points.length > 0)
}

export function summaryToMarkdown(summary: Summary, duration?: number): string {
  const lines = [`# ${summary.title}`, '']
  if (duration) lines.push(`- Duration: ${Math.floor(duration / 60)}:${Math.floor(duration % 60).toString().padStart(2, '0')}`, '')
  const intro = summaryIntroduction(summary.overview)
  if (intro.conclusions) lines.push('## 核心结论', '', normalizeSummaryMarkdown(intro.conclusions), '')
  lines.push('## Overview', '', normalizeSummaryMarkdown(intro.overview), '', '## Key Points by Topic', '')
  for (const [topic, points] of summaryChapters(summary)) {
    lines.push(`### ${topic}`, '')
    for (const point of points) {
      lines.push(normalizeSummaryMarkdown(point.summary), '')
      if (point.original_quote) {
        if (point.timestamp) lines.push(`Source · ${point.timestamp}`, '')
        lines.push(...point.original_quote.split('\n').map(line => `> ${line}`), '')
      }
    }
  }
  if (summary.takeaways.length) lines.push('## Takeaways', '', ...summary.takeaways.map(value => `- ${normalizeSummaryMarkdown(value)}`), '')
  return lines.join('\n')
}
