import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)]
const paths = [...new Set(assets.map(([, path]) => path))]
// Count the complete document, including embedded code, CSS and bootstrap.
// Include the small shared connection-feedback state and read-recovery hooks.
// Allow 0.5 KiB for cross-browser control sizing and responsive card rules.
// Allow 0.5 KiB for shared disclosure dismissal and touch navigation behavior.
// Allow 0.5 KiB for authentication pending-state feedback and integrated settings updates.
// Allow 0.5 KiB for detailed processing stages integrated with Editorial control states.
const budgetKiB = 194
const bytes = gzipSync(html).length + paths.reduce((sum, path) => sum + gzipSync(readFileSync(new URL('../dist' + path, import.meta.url))).length, 0)
console.log(`Initial compressed document and external assets: ${(bytes / 1024).toFixed(1)} KiB (budget: ${budgetKiB} KiB)`)
if (bytes > budgetKiB * 1024) throw new Error('Initial page assets exceed the loading budget. Keep rich formatting deferred.')
