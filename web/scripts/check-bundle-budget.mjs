import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"<>]+\.(?:js|css))"/g)]
const bytes = assets.reduce((sum, [, path]) => sum + gzipSync(readFileSync(new URL('../dist' + path, import.meta.url))).length, 0)
console.log(`Initial compressed assets: ${(bytes / 1024).toFixed(1)} KiB (budget: 150 KiB)`)
if (bytes > 150 * 1024) throw new Error('Initial page assets exceed the loading budget. Keep viewer dependencies deferred.')
