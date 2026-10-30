// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import ArticleNote,{articleEmbed} from '../src/components/ArticleNote'

it('embeds localized Spotify links using the canonical player URL',()=>{
 expect(articleEmbed('https://open.spotify.com/intl-zh/episode/08tccyLPpPurxtPPrezQGZ?si=tracking')?.src).toBe('https://open.spotify.com/embed/episode/08tccyLPpPurxtPPrezQGZ')
})
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers()})

it('shows standalone source cards, keeps inline citations and does not request embeds before a click',async()=>{
 await act(async()=>root.render(<ArticleNote markdown={'Before [inline citation](https://research.example/paper).\n\n[Full research](https://research.example/paper)\n\nhttps://www.youtube.com/watch?v=abcdefghijk\n\nFinal original condition.'}/>))
 expect(node.querySelectorAll('.article-link-card')).toHaveLength(2)
 expect(node.querySelector('p a')?.textContent).toBe('inline citation')
 expect(node.querySelector('iframe')).toBeNull()
 expect(node.textContent).toContain('Final original condition.')
 const load=[...node.querySelectorAll('button')].find(b=>b.textContent==='Load YouTube player')!
 await act(async()=>load.click())
 expect(node.querySelector('iframe')?.src).toBe('https://www.youtube-nocookie.com/embed/abcdefghijk')
 expect(node.querySelector('iframe')?.getAttribute('sandbox')).not.toContain('allow-top-navigation')
 expect(node.querySelector('.article-link-card a')?.getAttribute('href')).toBe('https://research.example/paper')
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Close player')!.click())
 expect(node.querySelector('iframe')).toBeNull()
})

it('never nests screenshot controls in a navigation link',async()=>{
 await act(async()=>root.render(<ArticleNote markdown={'[**![Original image](https://images.example/preview.jpg)**](https://images.example/full.jpg)\n\n*Image credit: Author*'}/>))
 expect(node.querySelector('a button')).toBeNull()
 expect(node.querySelector('button.reader-screenshot')).not.toBeNull()
 expect(node.querySelector('a')?.getAttribute('href')).toBe('https://images.example/full.jpg')
 expect(node.textContent).toContain('Image credit: Author')
})

it.each(['https://youtube.com.evil.example/watch?v=abcdefghijk','https://user:secret@youtube.com/watch?v=abcdefghijk','javascript:alert(1)','https://youtube.com:444/watch?v=abcdefghijk','https://example.com/embed/anything'])('does not turn %s into an iframe',href=>expect(articleEmbed(href)).toBeNull())
it.each([
 ['https://youtu.be/abcdefghijk','https://www.youtube-nocookie.com/embed/abcdefghijk'],
 ['https://youtu.be/abcdefghijk?t=1m30s','https://www.youtube-nocookie.com/embed/abcdefghijk?start=90'],
 ['https://www.youtube.com/watch?v=abcdefghijk&start=120','https://www.youtube-nocookie.com/embed/abcdefghijk?start=120'],
 ['https://www.bilibili.com/video/BV1234567890','https://player.bilibili.com/player.html?bvid=BV1234567890&autoplay=0'],
 ['https://www.bilibili.com/video/BV1234567890?p=2','https://player.bilibili.com/player.html?bvid=BV1234567890&autoplay=0&p=2'],
 ['https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ','https://open.spotify.com/embed/episode/08tccyLPpPurxtPPrezQGZ'],
])('recognizes %s', (href,src)=>expect(articleEmbed(href)?.src).toBe(src))

it('serves social article images from separate readable and original caches',async()=>{
 await act(async()=>root.render(<ArticleNote markdown={'Before.\n\n![Original chart](https://pbs.twimg.com/media/chart.jpg)\n\nFinal condition.'}/>))
 const image=node.querySelector('img')!
 expect(image.getAttribute('src')).toBe('/api/image-proxy?url=https%3A%2F%2Fpbs.twimg.com%2Fmedia%2Fchart.jpg&size=article')
 expect(node.querySelector('button.reader-screenshot')?.getAttribute('data-original-src')).toBe('/api/image-proxy?url=https%3A%2F%2Fpbs.twimg.com%2Fmedia%2Fchart.jpg&size=original')
 expect(node.textContent).toContain('Final condition.')
})

it('keeps signed generic article images on the same origin and enlarges only on demand',async()=>{
 const url='/api/article-image?url=https%3A%2F%2Fblog.example%2Fchart.png&expires=100&signature=abc&size=article'
 await act(async()=>root.render(<ArticleNote markdown={'![Source chart]('+url+')'}/>))
 expect(node.querySelector('img')?.getAttribute('src')).toBe(url)
 expect(node.querySelector('button.reader-screenshot')?.getAttribute('data-original-src')).toContain('size=original')
 expect(node.querySelectorAll('img')).toHaveLength(1)
})

it('offers a refresh for an expired article image capability instead of an endless retry',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(null,{status:403})))
 try{
  await act(async()=>root.render(<ArticleNote markdown={'![Chart](/api/article-image?url=https%3A%2F%2Fblog.example%2Fchart.png&expires=1&signature=expired)'}/>))
  await act(async()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
  expect(node.textContent).toContain('Image link expired')
  expect([...node.querySelectorAll('button')].some(button=>button.textContent==='Refresh image links')).toBe(true)
 }finally{vi.unstubAllGlobals()}
})

it('keeps an escaped year as prose while containing real large list numbers',async()=>{
 await act(async()=>root.render(<ArticleNote markdown={'2018\\. A year in a source paragraph.\n\n2018. A real list item.\n2019. Another item.\n\n## Next section\n\n1. A normal list item.'}/>))
 expect(node.querySelector('p')?.textContent).toBe('2018. A year in a source paragraph.')
 const lists=node.querySelectorAll('ol')
 expect(lists).toHaveLength(2)
 expect(lists[0].start).toBe(2018)
 expect(lists[0].classList.contains('wide-number-list')).toBe(true)
 expect(lists[0].children).toHaveLength(2)
 expect(lists[1].classList.contains('wide-number-list')).toBe(false)
})
