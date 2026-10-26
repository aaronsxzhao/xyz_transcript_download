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
  const match = overview.match(/^\s*### (?:核心结论|Key conclusions)\s*\r?\n([\s\S]*?)^### (?:节目概览|Episode overview)\s*\r?\n([\s\S]*)$/m)
  if (!match) return { conclusions: '', overview }
  const prefix=overview.slice(0,match.index).trim()
  // Advisory blockquotes are generated before the labelled introduction.
  // Preserve them in Overview while keeping the conclusions independently
  // readable. Arbitrary prose/code before these labels remains legacy content.
  if(prefix&&!prefix.split(/\r?\n/).every(line=>!line.trim()||/^\s*>/.test(line))) return { conclusions: '', overview }
  return { conclusions: match[1].trim(), overview: [prefix,match[2].trim()].filter(Boolean).join('\n\n') }
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
