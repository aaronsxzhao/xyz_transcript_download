// @vitest-environment jsdom
import React,{act,Profiler} from 'react'
import {createRoot} from 'react-dom/client'
import {it,expect,vi} from 'vitest'
import ScreenshotGallery from '../src/components/ScreenshotGallery'
vi.mock('../src/lib/reading',()=>({useDialog:()=>{}}))

it('renders a newly selected cached image as loading and fitted in its first commit',async()=>{
 const container=document.createElement('div');document.body.append(container);const root=createRoot(container)
 const scrollTo=HTMLElement.prototype.scrollTo;HTMLElement.prototype.scrollTo=vi.fn()
 const commits:{src:string|null;display:string;width:string}[]=[]
 try {
  await act(async()=>root.render(<Profiler id="gallery" onRender={()=>{
   const image=document.querySelector<HTMLImageElement>('.gallery-viewport img');if(image)commits.push({src:image.getAttribute('src'),display:image.style.display,width:image.style.width})
  }}><ScreenshotGallery images={[{src:'https://images.example/a.jpg',alt:'First'},{src:'https://images.example/b.jpg',alt:'Second'}]} initial={0} onClose={()=>{}}/></Profiler>))
  await act(async()=>document.querySelector('.gallery-viewport img')!.dispatchEvent(new Event('load')))
  await act(async()=>document.querySelector<HTMLButtonElement>('[aria-label="Zoom in"]')!.click())
  commits.length=0
  await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Next')!.click())
  expect(commits.find(c=>c.src==='https://images.example/b.jpg')).toMatchObject({display:'none',width:'auto'})
  await act(async()=>document.querySelector('.gallery-viewport img')!.dispatchEvent(new Event('load')))
  expect(document.querySelector<HTMLImageElement>('.gallery-viewport img')!.style.display).toBe('block')
 } finally {await act(async()=>root.unmount());container.remove();HTMLElement.prototype.scrollTo=scrollTo}
})
