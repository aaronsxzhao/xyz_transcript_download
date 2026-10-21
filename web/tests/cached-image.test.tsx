// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,expect,it,vi} from 'vitest'
import CachedImage from '../src/components/CachedImage'
let cleanup:()=>void
afterEach(()=>{cleanup?.();vi.useRealTimers()})
it('retains a placeholder while loading, shows cached images and resets for a new source',()=>{
 const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 cleanup=()=>{act(()=>root.unmount());node.remove()}
 const render=(src:string)=>act(()=>root.render(<CachedImage src={src} className="w-20 h-14"/>))
 render('https://image.xyzcdn.net/first');expect(node.querySelector('[data-image-state]')?.getAttribute('data-image-state')).toBe('loading')
 expect(node.querySelector('.cached-image-fallback')).not.toBeNull()
 act(()=>node.querySelector('img')!.dispatchEvent(new Event('load')))
 expect(node.querySelector('img')?.style.opacity).toBe('1')
 render('https://image.xyzcdn.net/second');expect(node.querySelector('img')?.style.opacity).toBe('0')
 expect(node.querySelector('.cached-image-fallback')).not.toBeNull()
})
it('retries a failed image once and keeps its reserved box after failure',async()=>{
 vi.useFakeTimers();const node=document.createElement('div');document.body.append(node);const root=createRoot(node)
 cleanup=()=>{act(()=>root.unmount());node.remove()}
 act(()=>root.render(<CachedImage src="https://image.xyzcdn.net/retry"/>))
 act(()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
 expect(node.querySelector('img')).toBeNull()
 await act(async()=>vi.advanceTimersByTimeAsync(3500))
 expect(node.querySelector('img')?.getAttribute('src')).toContain('&retry=1')
 act(()=>node.querySelector('img')!.dispatchEvent(new Event('error')))
 await act(async()=>vi.advanceTimersByTimeAsync(10000))
 expect(node.querySelector('img')).toBeNull();expect(node.querySelector('.cached-image-fallback')).not.toBeNull()
})
