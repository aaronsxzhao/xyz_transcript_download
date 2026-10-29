// @vitest-environment jsdom
import React, {act} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import AppearanceControls from '../src/components/AppearanceControls'
import {setAppearance} from '../src/lib/theme'
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{localStorage.clear();document.documentElement.dataset.design='classic';document.documentElement.dataset.theme='dark';node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.restoreAllMocks()})
it('keeps design and color independent and synchronizes every mounted control',async()=>{
 await act(async()=>root.render(<><AppearanceControls/><AppearanceControls/></>))
 await act(async()=>{await setAppearance('editorial','dark')})
 expect([...node.querySelectorAll('select')].map(el=>el.value)).toEqual(['editorial','editorial'])
 await act(async()=>{node.querySelector('button')!.click()})
 expect(document.documentElement.dataset.design).toBe('editorial')
 expect(document.documentElement.dataset.theme).toBe('light')
 expect(document.documentElement.classList.contains('dark')).toBe(false)
 expect(localStorage.getItem('xyz:design')).toBe('editorial')
 expect(localStorage.getItem('xyz:color-theme')).toBe('light')
 await act(async()=>{await setAppearance('classic','light')})
 expect(document.documentElement.dataset.theme).toBe('light')
})
it('keeps controls working when storage rejects writes',async()=>{
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked')})
 await act(async()=>root.render(<AppearanceControls/>))
 await act(async()=>{await setAppearance('editorial','light')})
 expect(node.querySelector('select')!.value).toBe('editorial')
 expect(node.querySelector('button')!.getAttribute('aria-label')).toBe('Switch to dark mode')
})
it('retains cross-tab synchronization after another control unmounts',async()=>{
 await act(async()=>root.render(<><AppearanceControls/><AppearanceControls/></>))
 await act(async()=>root.render(<><AppearanceControls/></>))
 localStorage.setItem('xyz:design','editorial');localStorage.setItem('xyz:color-theme','light')
 await act(async()=>{window.dispatchEvent(new StorageEvent('storage',{key:'xyz:design',storageArea:localStorage}));await new Promise(resolve=>setTimeout(resolve,0))})
 expect(node.querySelector('select')!.value).toBe('editorial')
 expect(document.documentElement.dataset.theme).toBe('light')
})
