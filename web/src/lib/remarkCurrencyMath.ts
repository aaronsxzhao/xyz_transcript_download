import type {} from 'remark-parse'
import type { Processor } from 'unified'
import type { Construct } from 'micromark-util-types'

/** Apply currency-safe boundaries to single-dollar math only.
 * Keep $$ blocks/inline math and the upstream tokenizer's code/escape handling.
 * A single-dollar closer cannot introduce another numeric amount; delimiters
 * must touch their formula. Otherwise let Markdown parse the original prose,
 * including emphasis, rather than recovering an already-rendered math node.
 */
export function remarkCurrencyMath(this: Processor) {
  for (const extension of this.data().micromarkExtensions || []) {
    const entry = extension.text?.[36]
    const constructs: Construct[] = entry ? (Array.isArray(entry) ? entry : [entry]) : []
    for (const construct of constructs) {
      if (construct.name !== 'mathText') continue
      const tokenize = construct.tokenize
      construct.tokenize = function (effects, ok, nok) {
        const context = this
        return tokenize.call(this, effects, code => {
          const token = context.events[context.events.length - 1]?.[1]
          const raw = token && context.sliceSerialize(token)
          if (raw?.startsWith('$') && !raw.startsWith('$$')) {
            const body = raw.slice(1, -1)
            if (/^\s|\s$/.test(body) || (code !== null && code >= 48 && code <= 57)) return nok(code)
          }
          return ok(code)
        }, nok)
      }
    }
  }
}
