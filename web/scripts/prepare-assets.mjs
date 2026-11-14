import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { gzipSync, brotliCompressSync, constants } from 'node:zlib'
import { createHash } from 'node:crypto'
import { minify } from 'vite'
import { documentProgram } from './document-program.mjs'
const root = new URL('../dist/', import.meta.url)
let html = readFileSync(new URL('index.html', root), 'utf8')
// Minify the existing pre-paint theme bootstrap, just like the startup shell.
const themeBootstrap = html.match(/<script>([\s\S]*?)<\/script>/)
if (themeBootstrap) {
  const theme = await minify('theme.js', themeBootstrap[1])
  if (theme.errors?.length) throw new Error('Theme bootstrap minification failed')
  html = html.replace(themeBootstrap[0], () => '<script>' + theme.code + '</script>')
}
const manifest = JSON.parse(readFileSync(new URL('manifest.json',root),'utf8'))
const program = await documentProgram(root,manifest)
const payload = JSON.stringify(program.modules).replace(/</g,'\\u003c')
// The normal path remains self-contained. Only a stalled document races a
// separately cached copy of the identical public module graph. No auth data is
// included, and a failed recovery request leaves the inline fallback intact.
// The .js suffix uses the existing immutable compressed-asset/CDN path; the
// response is parsed as JSON data, never imported or executed as a script.
const recoveryPath = '/assets/startup-program-' + createHash('sha256').update(payload).digest('hex').slice(0,16) + '.js'
const loader = await minify('document-loader.js', `
(function(){
  var started=false,entry=${JSON.stringify(program.entry)},timer,controller;
  window.__xyzDocumentStart=function(source){
    if(started || typeof source[entry]!=='string')return;
    started=true;clearTimeout(timer);if(controller)controller.abort();
    var imports={};
    for(var path in source){var blob=URL.createObjectURL(new Blob([source[path]],{type:'text/javascript'}));imports[path]=blob;imports['xyz-public:'+path]=blob;}
    var retry=new URLSearchParams(location.search).get('__xyz_boot');
    var optional=${JSON.stringify(readdirSync(new URL('assets/',root)).sort().filter(file=>file.endsWith('.js')&&!file.includes('.worker-')&&!Object.hasOwn(program.modules,'/assets/'+file)).map(file=>'/assets/'+file))};
    for(var path of optional)if(!imports[path]){var target=path+(retry?'?__xyz_retry='+encodeURIComponent(retry):'');imports['xyz-public:'+path]=new URL(target,location.origin).href;if(retry)imports[path]=target;}
    var map=document.createElement('script');map.type='importmap';map.textContent=JSON.stringify({imports:imports});document.head.appendChild(map);
    import(entry).catch(function(error){console.error('Application startup failed',error);window.__xyzEntryFailed=true;window.dispatchEvent(new Event('xyz:entry-error'))});
  };
  timer=setTimeout(function(){if(started)return;controller=new AbortController();var timeout=setTimeout(function(){controller.abort()},15000);fetch(${JSON.stringify(recoveryPath)},{credentials:'omit',signal:controller.signal}).then(function(response){if(!response.ok)throw Error('Startup recovery unavailable');return response.json()}).then(window.__xyzDocumentStart).catch(function(){}).finally(function(){clearTimeout(timeout)})},12000);
})()`)
if (loader.errors?.length) throw new Error('Document loader minification failed')
const setup = `<script data-document-program data-cfasync="false">window.__xyzDocumentStart(${payload})</script>`
writeFileSync(new URL('.'+recoveryPath, root), payload)
// No separate request is needed on healthy startup. Optional modules
// still use normal hashed public URLs and share the embedded React runtime.
html = html.replace(/<link rel="modulepreload"[^>]*>/g,'')
html = html.replace(/<script type="module"[^>]*src="[^"]+"[^>]*><\/script>/,'')
// Keep the small shell and early reads before the larger embedded program so
// streaming documents can paint navigation and start data reads immediately.
html = html.replace('</body>',()=>`<script data-entry="${program.entry}" data-cfasync="false">${loader.code}</script>`+setup+'</body>')

// The inline startup shell needs the same production minification as the app.
const startup = await minify('startup.js', readFileSync(new URL('../src/startup.js', import.meta.url), 'utf8'))
if (startup.errors?.length) throw new Error('Startup script minification failed')
html = html.replace('<!-- xyz-startup -->', () => '<script data-cfasync="false">' + startup.code + '</script>')
// Keep a disabled stylesheet marker: Vite detects links, not inline styles.
// Without it, a lazy component re-adds base CSS after the selected skin.
html = html.replace(/<link rel="stylesheet"[^>]*href="(\/assets\/[^\"]+\.css)"[^>]*>/g, (_, href) =>
  `<link rel="stylesheet" href="${href}" disabled data-inlined-style><style data-app-style data-asset="${href}">${readFileSync(new URL('../dist' + href, import.meta.url),'utf8')}</style>`)
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
