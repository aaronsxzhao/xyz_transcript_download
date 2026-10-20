import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { gzipSync, brotliCompressSync, constants } from 'node:zlib'
import { createHash } from 'node:crypto'
const root = new URL('../dist/', import.meta.url)
let html = readFileSync(new URL('index.html', root), 'utf8')
// WebKit can retain a failed module URL across document reloads. On explicit
// recovery only, map the whole public module graph to fresh URLs, including
// transitive dependencies. Ordinary visits keep stable cacheable filenames.
const modules = readdirSync(new URL('assets/', root)).filter(file=>file.endsWith('.js')).map(file=>'/assets/'+file)
const recovery = `<script>(function(){var retry=new URLSearchParams(location.search).get('__xyz_boot');if(!retry)return;var paths=${JSON.stringify(modules)};var map=document.createElement('script');map.type='importmap';map.textContent=JSON.stringify({imports:Object.fromEntries(paths.map(function(path){return [path,path+'?__xyz_retry='+encodeURIComponent(retry)]}))});document.head.appendChild(map)})()</script>`
html = html.replace('<head>', '<head>'+recovery)

html = html.replace('<!-- xyz-startup -->', '<script>' + readFileSync(new URL('../src/startup.js', import.meta.url), 'utf8') + '</script>')
html = html.replace(/<link rel="stylesheet"[^>]*href="(\/assets\/[^\"]+\.css)"[^>]*>/g, (_, href) =>
  `<style data-app-style data-asset="${href}">${readFileSync(new URL('../dist' + href, import.meta.url),'utf8')}</style>`)
html = html.replace(/<script type="module"([^>]+)>/g, '<script type="module"$1 onerror="window.__xyzEntryFailed=true;window.dispatchEvent(new Event(\'xyz:entry-error\'))">')
writeFileSync(new URL('index.html', root), html)
const workerSource = readFileSync(new URL('../src/service-worker.js', import.meta.url), 'utf8')
const version = createHash('sha256').update(html).update(workerSource).digest('hex').slice(0, 16)
const worker = workerSource.replace('__XYZ_VERSION__', version)
writeFileSync(new URL('sw.js', root), worker)
let plain = 0, compressed = 0
for (const file of readdirSync(new URL('assets/', root))) {
  if (!/\.(js|css)$/.test(file)) continue
  const path = new URL('assets/' + file, root)
  const content = readFileSync(path)
  const brotli = brotliCompressSync(content, {params:{[constants.BROTLI_PARAM_QUALITY]: 9}})
  writeFileSync(new URL('assets/' + file + '.br', root), brotli)
  writeFileSync(new URL('assets/' + file + '.gz', root), gzipSync(content, {level:9}))
  plain += content.length; compressed += brotli.length
}
console.log(`Prepared Brotli/gzip assets: ${plain} raw bytes → ${compressed} Brotli bytes`)
