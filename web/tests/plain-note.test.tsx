// @vitest-environment jsdom
import React, { act, Profiler } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import ReaderScreenshot from '../src/components/ReaderScreenshot'
import { ScreenshotRecoveryContext } from '../src/lib/screenshotRecovery'
import PlainNote from '../src/components/PlainNote'
import {extractNoteToc,normalizeNoteHeadings} from '../src/lib/noteMarkdown'
import {rehypeNoteHeadings} from '../src/lib/noteHeadingPlugin'

let cleanup: (() => void) | undefined
afterEach(() => { cleanup?.(); cleanup=undefined; vi.useRealTimers() })

it.each([0,1,5])('preserves ordered lists starting at %s', start => {
 const node=document.createElement('div');const root=createRoot(node)
 cleanup=()=>act(()=>root.unmount())
 act(()=>root.render(<PlainNote markdown={`${start}. Collect data\n${start+1}. Review results`}/>))
 expect(node.querySelector('ol')?.start).toBe(start)
 expect(node.querySelectorAll('li')).toHaveLength(2)
})

it('repairs duplicate markers in numbered headings without changing code, quotations or normal prose', () => {
 const title='优化模式识别的重要性'
 const source=`## 8. 学习\n\n### 8.2 #### ${title}\n\n保留 **非常重要** 的论述。\n\n### 8.3 ### 视频风格说明\n\n\`### 8.2 #### Literal\`\n\n\`\`\`md\n### 8.2 #### Literal\n\`\`\`\n\n> ### 8.2 #### Quoted original\n\n    ### 8.2 #### Indented code\n\n8.2 #### Plain text\n\n### C# and ## symbols\n`
 const expected=source.replace(`### 8.2 #### ${title}`,`### 8.2 ${title}`).replace('### 8.3 ### 视频风格说明','### 8.3 视频风格说明')
 expect(normalizeNoteHeadings(source)).toBe(expected)
 expect(normalizeNoteHeadings(expected)).toBe(expected)
 expect(normalizeNoteHeadings(source.replaceAll('\n','\r\n'))).toBe(expected.replaceAll('\n','\r\n'))
 const node=document.createElement('div');const root=createRoot(node)
 cleanup=()=>act(()=>root.unmount())
 act(()=>root.render(<PlainNote markdown={source}/>))
 const heading=node.querySelectorAll('h3')[0]
 expect(heading.textContent).toBe(`8.2 ${title}`)
 expect(extractNoteToc(source).find(item=>item.text===`8.2 ${title}`)?.slug).toBe(heading.id)
 expect(node.querySelector('p strong')?.textContent).toBe('非常重要')
 expect(node.querySelector('pre code')?.textContent).toBe('### 8.2 #### Literal')
})

it('keeps directory links unique and aligned with nested and suffixed headings in both renderers',()=>{
 const markdown='# Review\n\n> ## Review\n\n## Review\n\n### Review-1\n\n#### Review\n\n## Review\n\n## 🎯'
 const node=document.createElement('div');const root=createRoot(node)
 cleanup=()=>act(()=>root.unmount())
 act(()=>root.render(<PlainNote markdown={markdown}/>))
 const headings=Array.from(node.querySelectorAll('h1,h2,h3,h4'))
 expect(new Set(headings.map(h=>h.id)).size).toBe(headings.length)
 expect(headings.every(h=>h.id.length>0)).toBe(true)
 const visible=headings.filter(h=>h.tagName!=='H4')
 expect(extractNoteToc(markdown).map(h=>h.slug)).toEqual(visible.map(h=>h.id))
 const tree={children:headings.map(h=>({tagName:h.tagName.toLowerCase(),properties:{},children:[{value:h.textContent||''}]}))}
 rehypeNoteHeadings()(tree)
 expect(tree.children.map(h=>(h.properties as {id:string}).id)).toEqual(headings.map(h=>h.id))
})

it('renders semantic Markdown and matching duplicate anchors without optional formatting', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'# 交易 **复盘**\n\n## 目录\n- [趋势](#趋势)\n\n---\n\n## 趋势\n\n**确认**后操作。\n\n- 观察\n  - 管理风险\n\n| 信号 | 行动 |\n| --- | --- |\n| 突破 | 等待 |\n\n## 趋势'}/>))
  expect(node.querySelector('h1')?.textContent).toBe('交易 复盘')
  expect(Array.from(node.querySelectorAll('h2'),h=>h.id)).toEqual(['趋势','趋势-1'])
  expect(node.querySelector('p strong')?.textContent).toBe('确认')
  expect(node.querySelector('li li')?.textContent).toContain('管理风险')
  expect(node.querySelector('table tbody td')?.textContent).toBe('突破')
  expect(node.textContent).not.toContain('目录')
})

it('keeps dangerous links and HTML inert while preserving readable labels', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'[unsafe](javascript:alert) [safe](https://example.com)\n\n<iframe src="https://example.com"></iframe>'}/>))
  expect(node.querySelectorAll('a')).toHaveLength(1)
  expect(node.querySelector('a')?.href).toBe('https://example.com/')
  expect(node.querySelector('iframe')).toBeNull()
  expect(node.textContent).toContain('unsafe')
})

it('keeps saved text readable and escapes HTML when formatting is unavailable', () => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'Saved note\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>'}/>))
  expect(node.textContent).toContain('Saved note')
  expect(node.textContent).toContain('<script>')
  expect(node.querySelector('script, img')).toBeNull()
})

it('loads private and HTTPS screenshots in fallback without allowing executable image URLs', () => {
  vi.useFakeTimers()
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  act(()=>root.render(<PlainNote markdown={'![private](/data/screenshots/a.png?signature=test)\n![remote](https://example.com/a.png)\n![unsafe](javascript:alert)\n![embedded](data:image/svg+xml,unsafe)'}/>))
  expect(Array.from(node.querySelectorAll('img'), image=>image.getAttribute('src'))).toEqual(['/data/screenshots/a.png?signature=test&preview=true','https://example.com/a.png'])
  expect(node.textContent).toContain('unsafe')
})

it.each([403,404])('explains image HTTP %s instead of offering endless retries', async status => {
  const node=document.createElement('div');const root=createRoot(node)
  cleanup=()=>act(()=>root.unmount())
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status})))
  try {
    act(()=>root.render(<ReaderScreenshot src="/data/screenshots/private.png?signature=test" alt="chart"/>))
    await act(async()=>{node.querySelector('img')!.dispatchEvent(new Event('error')); await Promise.resolve()})
    await vi.waitFor(()=>expect(node.textContent).toContain(status===403?'Image link expired':'Source image is missing'))
    expect(node.textContent).not.toContain('Retry image')
  } finally { vi.unstubAllGlobals() }
})

it('opens the owning reader recovery action for a missing image without requiring obsolete DOM markup',async()=>{
 const node=document.createElement('div');const root=createRoot(node);const recover=vi.fn()
 cleanup=()=>act(()=>root.unmount())
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})))
 try {
  await act(async()=>root.render(<ScreenshotRecoveryContext.Provider value={recover}><ReaderScreenshot src="/data/screenshots/missing.png"/></ScreenshotRecoveryContext.Provider>))
  await act(async()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
  await vi.waitFor(()=>expect(node.textContent).toContain('Open screenshot recovery'))
  await act(async()=>node.querySelector('button')!.click())
  expect(recover).toHaveBeenCalledOnce()
 }finally{vi.unstubAllGlobals()}
})

it('renders a replacement image without carrying the previous failure into its first commit',async()=>{
 const node=document.createElement('div');const root=createRoot(node)
 cleanup=()=>act(()=>root.unmount())
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})))
 const commits:{image:string|null;text:string|null}[]=[]
 const render=(src:string)=>root.render(<Profiler id="image" onRender={()=>commits.push({image:node.querySelector('img')?.getAttribute('src')||null,text:node.textContent})}><ReaderScreenshot src={src}/></Profiler>)
 try{
  await act(async()=>render('/data/screenshots/old.png'))
  await act(async()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
  expect(node.textContent).toContain('Source image is missing')
  commits.length=0
  await act(async()=>render('/data/screenshots/new.png'))
  expect(commits[0].image).toBe('/data/screenshots/new.png?preview=true')
  expect(commits[0].text).not.toContain('Source image is missing')
 }finally{vi.unstubAllGlobals()}
})

it('ignores an old image diagnostic that finishes after the next image fails',async()=>{
 const node=document.createElement('div');const root=createRoot(node)
 cleanup=()=>act(()=>root.unmount())
 let old!:(response:Response)=>void,current!:(response:Response)=>void
 vi.stubGlobal('fetch',vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{old=resolve})).mockImplementationOnce(()=>new Promise(resolve=>{current=resolve})))
 try{
  await act(async()=>root.render(<ReaderScreenshot src="/data/screenshots/old.png"/>))
  await act(async()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
  await act(async()=>root.render(<ReaderScreenshot src="/data/screenshots/new.png"/>))
  await act(async()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
  await act(async()=>old(new Response('',{status:404})))
  expect(node.textContent).toContain('Checking image')
  await act(async()=>current(new Response('',{status:403})))
  expect(node.textContent).toContain('Image link expired')
 }finally{vi.unstubAllGlobals()}
})
