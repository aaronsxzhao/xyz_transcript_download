import {Lexer} from 'marked'
import type { KeyPoint, Summary } from './api'

/** CommonMark treats **中文。**后文 as literal asterisks. Move only the
 * closing punctuation outside emphasis, leaving text and code unchanged. */
export function normalizeSummaryMarkdown(markdown: string): string {
  markdown = deduplicateHeadings(markdown)
  const newline = markdown.includes('\r\n') ? '\r\n' : '\n'
  let cursor = 0, output = ''
  for (const token of Lexer.lex(markdown)) {
    const raw = token.raw.replace(/\n/g, newline)
    const start = markdown.indexOf(raw, cursor)
    if (start < 0) return markdown
    output += markdown.slice(cursor, start)
    // Code, HTML, quotations and nested block containers retain source bytes.
    // Inline parsing also protects multi-backtick code and link destinations.
    output += ['paragraph', 'heading', 'table'].includes(token.type)
      ? Lexer.lexInline(raw).map(part => part.type === 'text'
        ? part.raw.replace(/(?<!\\)\*\*(?=\S)([^*\n]+?)([，。；：！？、,.!?;:]+)\*\*(?=[\p{L}\p{N}])/gu, '**$1**$2')
        : part.raw).join('') : raw
    cursor = start + raw.length
  }
  return output + markdown.slice(cursor)
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
  let previous = '', cursor = 0, output = '', kept = 0
  const newline = markdown.includes('\r\n') ? '\r\n' : '\n'
  for (const token of Lexer.lex(markdown)) {
    // Lexer omits reference definitions. Edit original spans, not token output.
    const raw = token.raw.replace(/\n/g, newline)
    const start = markdown.indexOf(raw, cursor)
    if (start < 0) return markdown
    if (markdown.slice(cursor, start).trim()) previous = ''
    cursor = start + raw.length
    if (token.type === 'space') continue
    const key = token.type === 'heading' ? token.depth + ':' + token.text : ''
    if (key && key === previous) {
      output += markdown.slice(kept, start)
      kept = cursor
    }
    previous = key
  }
  return output + markdown.slice(kept)
}

/** Count visible top-level arguments, rather than storage rows or nested headings. */
export function summaryPointCount(points: KeyPoint[]): number {
  return points.reduce((total, point) => {
    const depths = Lexer.lex(deduplicateHeadings(point.summary)).flatMap(token => token.type === 'heading' ? [token.depth] : [])
    const depth = Math.min(...depths)
    return total + (depths.filter(value => value === depth).length || Number(!!point.summary.trim()))
  }, 0)
}
