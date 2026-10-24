import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)]
const paths = [...new Set(assets.map(([, path]) => path))]
// Count the complete document, including embedded code, CSS and bootstrap.
// Allow 1 KiB for the X/Substack routing and original-content reader controls.
const bytes = gzipSync(html).length + paths.reduce((sum, path) => sum + gzipSync(readFileSync(new URL('../dist' + path, import.meta.url))).length, 0)
console.log(`Initial compressed document and external assets: ${(bytes / 1024).toFixed(1)} KiB (budget: 191 KiB)`)
if (bytes > 191 * 1024) throw new Error('Initial page assets exceed the loading budget. Keep rich formatting deferred.')
