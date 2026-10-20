import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)]
const paths = [...new Set(assets.map(([, path]) => path))]
const inlineStyles = [...html.matchAll(/<style data-app-style[^>]*>([\s\S]*?)<\/style>/g)].reduce((sum, match)=>sum+gzipSync(match[1]).length,0)
const bytes = inlineStyles + paths.reduce((sum, path) => sum + gzipSync(readFileSync(new URL('../dist' + path, import.meta.url))).length, 0)
console.log(`Initial compressed program and styles: ${(bytes / 1024).toFixed(1)} KiB (budget: 175 KiB; all page controllers included)`)
if (bytes > 175 * 1024) throw new Error('Initial page assets exceed the loading budget. Keep rich formatting deferred.')
