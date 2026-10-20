import { readFileSync } from 'node:fs'
import { posix } from 'node:path'
import { init, parse } from 'es-module-lexer'

/** Embed the static module graph without bundling optional formatters into it.
 * Import maps keep one module identity when optional modules import the runtime.
 */
export async function documentProgram(root, manifest) {
  await init
  const files = new Set()
  const visit = key => {
    const entry = manifest[key]
    if (!entry || files.has(entry.file)) return
    files.add(entry.file)
    for (const child of entry.imports || []) visit(child)
  }
  visit('index.html')
  const modules = {}
  for (const file of files) {
    if (!file.endsWith('.js')) continue
    let source = readFileSync(new URL(file, root), 'utf8')
    const changes = []
    for (const entry of parse(source)[0]) {
      if (entry.type === 'import-meta') {
        // Blob modules have no relative URL base. Preserve the published URL
        // for Vite's optional preload/CSS resolution without issuing a request.
        const property = source.slice(entry.end).match(/^\.(url|resolve)\b/)?.[1]
        if (property) changes.push({start:entry.start,end:entry.end+property.length+1,
          value:property === 'url' ? `(new URL(${JSON.stringify('/'+file)},location.origin).href)` : 'undefined'})
      } else if (entry.specifier?.startsWith('.')) {
        const path = 'xyz-public:/' + posix.normalize(posix.join(posix.dirname(file), entry.specifier))
        changes.push({start:entry.start,end:entry.end,value:entry.type === 'dynamic' ? JSON.stringify(path) : path})
      }
    }
    for (const change of changes.sort((a,b)=>b.start-a.start)) source=source.slice(0,change.start)+change.value+source.slice(change.end)
    modules['/'+file] = source
  }
  return {modules, entry:'/'+manifest['index.html'].file}
}
