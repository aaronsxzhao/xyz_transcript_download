// @vitest-environment jsdom
import {summaryToMarkdown} from '../src/lib/podcastMarkdown'
import {expect,it} from 'vitest'
import {summaryIntroduction,summaryChapters} from '../src/lib/summaryReading'
const point=(topic:string,summary:string)=>({topic,summary,original_quote:'line one\nline two',timestamp:'28:29'})
it('leaves legacy and ambiguous overviews intact',()=>{
 for(const overview of ['Legacy paragraphs.','### 核心结论\nOnly one section.','Earlier text\n### 核心结论\n- Claim\n### 节目概览\nBody']) expect(summaryIntroduction(overview)).toEqual({conclusions:'',overview})
 const parts=summaryIntroduction('### 核心结论\n- Conditional claim.\n\n### 节目概览\nParagraph one.\n\nParagraph two.')
 expect(parts).toEqual({conclusions:'- Conditional claim.',overview:'Paragraph one.\n\nParagraph two.'})
})
it('retains multiple same-chapter details and unmatched legacy topics in declared order',()=>{
 const summary={episode_id:'e',title:'Original episode',overview:'Legacy overview',topics:['Chapter B','Chapter A'],key_points:[point('Chapter A','#### A1\n\nFirst detail.'),point('Chapter A','#### A2\n\nSecond detail.'),point('Chapter B','B detail'),point('Legacy unmatched','Legacy detail')],takeaways:['Track the conditions.']}
 expect(summaryChapters(summary).map(([topic,points])=>[topic,points.length])).toEqual([['Chapter B',1],['Chapter A',2],['Legacy unmatched',1]])
 const markdown=summaryToMarkdown(summary)
 expect(markdown).toContain('#### A1\n\nFirst detail.')
 expect(markdown).toContain('#### A2\n\nSecond detail.')
 expect(markdown).not.toContain('**####')
 expect(markdown).toContain('> line one\n> line two')
 expect(markdown).toContain('28:29')
})

it('renders Chinese emphasis while preserving code samples and original quote text',async()=>{
 const {normalizeSummaryMarkdown}=await import('../src/lib/summaryReading')
 const {markdownToSafeHtml}=await import('../src/lib/safeHtml')
 const source='**供需是基础。**天气是催化。\n\n`**原样。**代码`\n\n```text\n**保留。**示例\n```'
 const normalized=normalizeSummaryMarkdown(source)
 expect(normalized).toContain('**供需是基础**。天气是催化。')
 expect(normalized).toContain('`**原样。**代码`')
 expect(normalized).toContain('```text\n**保留。**示例\n```')
 expect(await markdownToSafeHtml(normalized)).toContain('<strong>供需是基础</strong>。天气是催化。')
 const summary={episode_id:'e',title:'Title',overview:'Overview',topics:['Chapter'],key_points:[{...point('Chapter',source),original_quote:'**原话。**不能改'}],takeaways:[]}
 expect(summaryToMarkdown(summary)).toContain('> **原话。**不能改')
})

it('recognizes English overview headings and preserves English in Markdown export',()=>{
 const overview='### Key conclusions\n- A conditional claim.\n\n### Episode overview\nAn English source explanation.'
 expect(summaryIntroduction(overview)).toEqual({conclusions:'- A conditional claim.',overview:'An English source explanation.'})
 const markdown=summaryToMarkdown({episode_id:'e',title:'Title',overview,topics:[],key_points:[],takeaways:[]})
 expect(markdown).toContain('## Key conclusions')
 expect(markdown).not.toContain('核心结论')
})
it('keeps advisory notices while separating the core conclusions',()=>{
 const warning='> ℹ️ Notes were generated, but the full-source coverage review did not complete.'
 const overview=warning+'\n\n### Key conclusions\n- A conditional claim.\n\n### Episode overview\nFull overview.'
 expect(summaryIntroduction(overview)).toEqual({conclusions:'- A conditional claim.',overview:warning+'\n\nFull overview.'})
})
it('keeps multiline takeaways inside their own list item in Markdown export',async()=>{
 const {markdownToSafeHtml}=await import('../src/lib/safeHtml')
 const markdown=summaryToMarkdown({episode_id:'e',title:'Title',overview:'Overview',topics:[],key_points:[],takeaways:['First conclusion.\n\nA necessary condition.','Second conclusion.']})
 const div=document.createElement('div');div.innerHTML=await markdownToSafeHtml(markdown)
 expect(div.querySelectorAll('ul>li')).toHaveLength(2)
 expect(div.querySelector('li')?.textContent).toContain('A necessary condition.')
})
