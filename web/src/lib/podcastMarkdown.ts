import type {Summary} from './api'
import {summaryIntroduction,summaryChapters,normalizeSummaryMarkdown} from './summaryReading'

export function summaryToMarkdown(summary: Summary, duration?: number): string {
  const lines = [`# ${summary.title}`, '']
  if (duration && Number.isFinite(duration) && duration>0) lines.push(`- Duration: ${Math.floor(duration / 60)}:${Math.floor(duration % 60).toString().padStart(2, '0')}`, '')
  const intro = summaryIntroduction(summary.overview)
  if (intro.conclusions) lines.push(/### Key conclusions/.test(summary.overview) ? '## Key conclusions' : '## 核心结论', '', normalizeSummaryMarkdown(intro.conclusions), '')
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
  if (summary.takeaways.length) lines.push('## Takeaways', '', ...summary.takeaways.map(value => `- ${normalizeSummaryMarkdown(value).replace(/\r?\n/g,'\n  ')}`), '')
  return lines.join('\n')
}
