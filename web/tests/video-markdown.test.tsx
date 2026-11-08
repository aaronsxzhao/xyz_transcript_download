// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import MarkdownPreview from '../src/components/video/MarkdownPreview'
import ReaderDetails from '../src/components/video/ReaderDetails'

vi.mock('../src/components/ReaderScreenshot',()=>({default:({src,alt}:any)=><img src={src} alt={alt}/>}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.unstubAllGlobals()})

it('formats saved notes without a second processing UI or requiring a completed task',async()=>{
 await act(async()=>root.render(<MarkdownPreview markdown={'# Saved lesson\n\n**Complete** original explanation.\n\n![Chart](https://example.com/chart.png)\n\n## Next steps\n\n- Read again'}/>))
 expect(node.querySelector('[data-rendering="formatted"] h1')?.textContent).toBe('Saved lesson')
 expect(node.querySelector('strong')?.textContent).toBe('Complete')
 expect(node.querySelector('img')?.getAttribute('src')).toBe('https://example.com/chart.png')
 expect(node.querySelectorAll('button,[role=progressbar]')).toHaveLength(0)
 expect(node.textContent).not.toContain('Processing failed')
})

it('handles malformed source anchors without throwing and still scrolls valid anchors',async()=>{
 const scroll=vi.fn();vi.stubGlobal('scrollTo',vi.fn())
 await act(async()=>root.render(<MarkdownPreview markdown={'[Broken](#%ZZ)\n\n[Working](#next)\n\n## Next'}/>))
 const heading=node.querySelector('h2')!;heading.scrollIntoView=scroll
 const links=node.querySelectorAll('a')
 const broken=new MouseEvent('click',{bubbles:true,cancelable:true})
 await act(async()=>links[0].dispatchEvent(broken))
 expect(broken.defaultPrevented).toBe(false)
 const valid=new MouseEvent('click',{bubbles:true,cancelable:true})
 await act(async()=>links[1].dispatchEvent(valid))
 expect(valid.defaultPrevented).toBe(true)
 expect(scroll).toHaveBeenCalledWith({block:'start'})
})

it('labels text imports as original content rather than a missing model or zero-length recording',async()=>{
 await act(async()=>root.render(<ReaderDetails kind="source" task={{id:'post',style:'original',platform:'substack',model:'',duration:0,formats:['original'],url:'https://writer.substack.com/p/post'} as any} selectedVersion="" onVersion={()=>{}} onClose={()=>{}} onRestored={()=>{}}/>))
 expect(node.textContent).toContain('No AI used · original text')
 expect(node.textContent).not.toContain('Not recorded')
 expect(node.textContent).not.toContain('0:00')
})

it('shows the selected saved version model rather than the latest model',async()=>{
 await act(async()=>root.render(<ReaderDetails kind="source" task={{id:'note',style:'detailed',platform:'youtube',model:'latest-model',duration:120,formats:['summary'],versions:[{id:'old',style:'brief',model_name:'historical-model'}]} as any} selectedVersion="old" onVersion={()=>{}} onClose={()=>{}} onRestored={()=>{}}/>))
 expect(node.textContent).toContain('historical-model')
 expect(node.textContent).not.toContain('latest-model')
 expect(node.textContent).toContain('Not recorded for saved versions')
})

it('does not invent a saved version model when its metadata is unavailable',async()=>{
 await act(async()=>root.render(<ReaderDetails kind="source" task={{id:'note',platform:'youtube',model:'latest-model',duration:120,formats:['summary'],versions:[]} as any} selectedVersion="old" onVersion={()=>{}} onClose={()=>{}} onRestored={()=>{}}/>))
 expect(node.textContent).toContain('Not recorded')
 expect(node.textContent).not.toContain('latest-model')
})

it('omits only the matching leading reader title and preserves later source headings and anchors',async()=>{
 await act(async()=>root.render(<MarkdownPreview readerTitle="Saved lesson" markdown={'# **Saved lesson**\n\n## Actual chapter\n\nComplete source content.\n\n# Saved lesson'}/>))
 expect(node.querySelectorAll('h1')).toHaveLength(1)
 expect(node.querySelector('h1')?.id).toBe('saved-lesson-1')
 expect(node.querySelector('h2')?.textContent).toBe('Actual chapter')
 expect(node.textContent).toContain('Complete source content.')
})

it('keeps currency and emphasis intact after lazy math loads, including mixed formulas',async()=>{
 const markdown='成本 **$100**，权利金 **$5**，目标 **$150**。\n\nFrom $10 to $20; fee $5 and formula $x^2$.\n\nMath: $2 + 2$, $100$, $$ x + y $$.\n\n```text\n$100 to $5\n```\n\nInline `$10 to $20`, escaped \\$30 and \\$40.'
 await act(async()=>root.render(<MarkdownPreview markdown={markdown}/>))
 await vi.waitFor(()=>expect(node.querySelectorAll('.katex')).toHaveLength(4))
 expect([...node.querySelectorAll('strong')].map(e=>e.textContent)).toEqual(['$100','$5','$150'])
 expect(node.textContent).toContain('From $10 to $20; fee $5 and formula')
 expect(node.querySelector('pre')?.textContent).toContain('$100 to $5')
 expect(node.textContent).toContain('Inline $10 to $20, escaped $30 and $40.')
 expect(node.querySelectorAll('.katex-error')).toHaveLength(0)
})

it('keeps display math and LaTeX while treating spaced single dollars as prose',async()=>{
 const markdown=String.raw`Literal $ x $ and $ y $.

Inline $\frac{a}{b}$.

$$
E = mc^2
$$

Padded double-dollar math: $$ x + y $$.`
 await act(async()=>root.render(<MarkdownPreview markdown={markdown}/>))
 await vi.waitFor(()=>expect(node.querySelectorAll('.katex')).toHaveLength(3))
 expect(node.textContent).toContain('Literal $ x $ and $ y $.')
 expect(node.querySelectorAll('.katex-display')).toHaveLength(1)
 expect(node.querySelectorAll('.katex-error')).toHaveLength(0)
})
