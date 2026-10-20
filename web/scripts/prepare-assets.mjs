import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { gzipSync, brotliCompressSync, constants } from 'node:zlib'
import { createHash } from 'node:crypto'
import { documentProgram } from './document-program.mjs'
const root = new URL('../dist/', import.meta.url)
let html = readFileSync(new URL('index.html', root), 'utf8')
const manifest = JSON.parse(readFileSync(new URL('manifest.json',root),'utf8'))
const program = await documentProgram(root,manifest)
const payload = JSON.stringify(program.modules).replace(/</g,'\\u003c')
const setup = `<script data-document-program data-cfasync="false">(function(){var source=${payload};var imports={};for(var path in source){var blob=URL.createObjectURL(new Blob([source[path]],{type:'text/javascript'}));imports[path]=blob;imports['xyz-public:'+path]=blob;}var retry=new URLSearchParams(location.search).get('__xyz_boot');var optional=${JSON.stringify(readdirSync(new URL('assets/',root)).sort().filter(file=>file.endsWith('.js')).map(file=>'/assets/'+file))};for(var path of optional)if(!imports[path]){var target=path+(retry?'?__xyz_retry='+encodeURIComponent(retry):'');imports['xyz-public:'+path]=new URL(target,location.origin).href;if(retry)imports[path]=target;}var map=document.createElement('script');map.type='importmap';map.textContent=JSON.stringify({imports:imports});document.head.appendChild(map)})()</script>`
// No separate request is needed to evaluate the application. Optional modules
// still use normal hashed public URLs and share the embedded React runtime.
html = html.replace(/<link rel="modulepreload"[^>]*>/g,'')
html = html.replace(/<script type="module"[^>]*src="[^"]+"[^>]*><\/script>/,'')
// Keep the small shell and early reads before the larger embedded program so
// streaming documents can paint navigation and start data reads immediately.
html = html.replace('</body>',()=>setup+`<script type="module" data-cfasync="false" data-entry="${program.entry}">import(${JSON.stringify(program.entry)}).catch(function(error){console.error('Application startup failed',error);window.__xyzEntryFailed=true;window.dispatchEvent(new Event('xyz:entry-error'))})</script></body>`)

html = html.replace('<!-- xyz-startup -->', () => '<script data-cfasync="false">' + readFileSync(new URL('../src/startup.js', import.meta.url), 'utf8') + '</script>')
html = html.replace(/<link rel="stylesheet"[^>]*href="(\/assets\/[^\"]+\.css)"[^>]*>/g, (_, href) =>
  `<style data-app-style data-asset="${href}">${readFileSync(new URL('../dist' + href, import.meta.url),'utf8')}</style>`)
html = html.replace(/<script type="module"([^>]+)>/g, '<script type="module"$1 onerror="window.__xyzEntryFailed=true;window.dispatchEvent(new Event(\'xyz:entry-error\'))">')
html = html.replace(/^[ \t]+$/gm,'')
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
