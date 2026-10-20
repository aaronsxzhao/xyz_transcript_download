import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)]
const paths = [...new Set(assets.map(([, path]) => path))]
// Count the complete document, including embedded code, CSS and bootstrap.
const bytes = gzipSync(html).length + paths.reduce((sum, path) => sum + gzipSync(readFileSync(new URL('../dist' + path, import.meta.url))).length, 0)
console.log(`Initial compressed document and external assets: ${(bytes / 1024).toFixed(1)} KiB (budget: 175 KiB)`)
if (bytes > 175 * 1024) throw new Error('Initial page assets exceed the loading budget. Keep rich formatting deferred.')
