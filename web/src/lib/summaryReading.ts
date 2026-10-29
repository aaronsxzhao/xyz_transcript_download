import {Lexer, type Tokens} from 'marked'
import type { KeyPoint, Summary } from './api'

/** CommonMark treats **中文。**后文 as literal asterisks. Move only the
 * closing punctuation outside emphasis, leaving text and code unchanged. */
export function normalizeSummaryMarkdown(markdown: string): string {
  return deduplicateHeadings(markdown).split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).map((part, index) => index % 2 ? part : part.replace(/(?<!\\)\*\*(?=\S)([^*\n]+?)([，。；：！？、,.!?;:]+)\*\*(?=[\p{L}\p{N}])/gu, '**$1**$2')).join('')
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

/** Top-level Markdown tokens exclude headings inside quotes and code. */
function deduplicateHeadings(markdown: string): string {
  let previous = ''
  return Lexer.lex(markdown).map(token => {
    if (token.type === 'space') return token.raw
    if (token.type === 'heading') {
      const key = token.depth + ':' + token.text
      const duplicate = previous === key
      previous = key
      return duplicate ? '' : token.raw
    }
    previous = ''
    return token.raw
  }).join('')
}

/** Count visible top-level arguments, rather than storage rows or nested headings. */
export function summaryPointCount(points: KeyPoint[]): number {
  return points.reduce((total, point) => {
    const tokens = Lexer.lex(deduplicateHeadings(point.summary))
    const headings = tokens.filter((token): token is Tokens.Heading => token.type === 'heading')
    if (!headings.length) return total + (point.summary.trim() ? 1 : 0)
    const depth = Math.min(...headings.map(token => token.depth))
    const count = headings.filter(token => token.depth === depth).length
    const first = tokens.findIndex(token => token.type === 'heading')
    const prefix = tokens.slice(0, first).some(token => token.type !== 'space')
    return total + count + (prefix ? 1 : 0)
  }, 0)
}
