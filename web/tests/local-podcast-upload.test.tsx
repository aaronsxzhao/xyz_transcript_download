// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import LocalPodcastUpload from '../src/components/LocalPodcastUpload'
import {uploadLocalPodcastAudio} from '../src/lib/api'
vi.mock('../src/lib/api',()=>({uploadLocalPodcastAudio:vi.fn()}))
const notify=vi.hoisted(()=>vi.fn())
vi.mock('../src/components/Toast',()=>({useToast:()=>({addToast:notify})}))
let root:ReturnType<typeof createRoot>,node:HTMLDivElement
beforeEach(()=>{vi.resetAllMocks();localStorage.clear();sessionStorage.clear();node=document.createElement('div');document.body.append(node);root=createRoot(node)})
afterEach(()=>{act(()=>root.unmount());node.remove()})
it('retains the upload failure message and allows choosing the same file again',async()=>{
 const changed=vi.fn()
 vi.mocked(uploadLocalPodcastAudio).mockRejectedValue(new Error('Audio format not supported'))
 await act(async()=>root.render(<LocalPodcastUpload onUploaded={changed}/>))
 const input=node.querySelector<HTMLInputElement>('input[type=file]')!
 Object.defineProperty(input,'files',{configurable:true,value:[new File(['fixture'],'lesson.wav')]})
 for(let attempt=0;attempt<2;attempt++){
  await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})))
  expect(input.value).toBe('');expect(input.disabled).toBe(false)
 }
 expect(uploadLocalPodcastAudio).toHaveBeenCalledTimes(2)
 expect(notify).toHaveBeenCalledWith(expect.objectContaining({type:'error',message:'Audio format not supported'}))
 expect(changed).not.toHaveBeenCalled()
})
