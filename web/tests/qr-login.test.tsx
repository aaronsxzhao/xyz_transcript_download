// @vitest-environment jsdom
import React,{act} from 'react'
import {createRoot} from 'react-dom/client'
import {MemoryRouter} from 'react-router-dom'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Settings from '../src/pages/Settings'
import {bilibiliQrGenerate,bilibiliQrPoll,fetchSettings,fetchAllCookies} from '../src/lib/api'

vi.mock('../src/lib/api',async original=>({...await original<object>(),fetchSettings:vi.fn(),fetchAllCookies:vi.fn(),bilibiliQrGenerate:vi.fn(),bilibiliQrPoll:vi.fn()}))
vi.mock('../src/contexts/AuthContext',()=>({useAuth:()=>({authEnabled:true})}))
vi.mock('../src/lib/pageTiming',()=>({usePageTiming:()=>{}}))
vi.mock('qrcode.react',()=>({QRCodeSVG:({value}:{value:string})=><div data-qr={value}/>}))
let node:HTMLDivElement,root:ReturnType<typeof createRoot>
beforeEach(()=>{
 vi.resetAllMocks();localStorage.clear();sessionStorage.clear();vi.useFakeTimers()
 vi.mocked(fetchSettings).mockResolvedValue({whisper_mode:'api',whisper_model:'whisper-large-v3-turbo',llm_model:'openai/gpt-oss-120b',llm_provider:'groq',groq_available:true,check_interval:86400} as any)
 vi.mocked(fetchAllCookies).mockResolvedValue({cookies:[]} as any)
 vi.mocked(bilibiliQrPoll).mockResolvedValue({status:'waiting',message:'Waiting for scan'})
 node=document.createElement('div');document.body.append(node);root=createRoot(node)
})
afterEach(()=>{act(()=>root.unmount());node.remove();vi.useRealTimers()})
async function mount(){
 await act(async()=>root.render(<MemoryRouter><Settings/></MemoryRouter>))
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent==='Platform Accounts')!.click())
}
const button=(label:string)=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()===label)!

it('does not let an old QR generation overwrite a new login after cancellation',async()=>{
 let finish!:(value:any)=>void
 vi.mocked(bilibiliQrGenerate).mockResolvedValueOnce({qr_url:'https://passport.bilibili.com/first',qrcode_key:'first'})
  .mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
  .mockResolvedValueOnce({qr_url:'https://passport.bilibili.com/current',qrcode_key:'current'})
 await mount();await act(async()=>button('Generate QR Code').click())
 await act(async()=>button('Refresh now').click())
 // Switching away cancels generation 2. Start generation 3 for the same platform.
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='YouTube')!.click())
 await act(async()=>[...node.querySelectorAll('button')].find(b=>b.textContent?.trim()==='BiliBili')!.click())
 await act(async()=>button('Generate QR Code').click())
 await act(async()=>finish({qr_url:'https://passport.bilibili.com/stale',qrcode_key:'stale'}))
 expect(node.querySelector('[data-qr]')?.getAttribute('data-qr')).toBe('https://passport.bilibili.com/current')
 await act(async()=>vi.advanceTimersByTimeAsync(2100))
 expect(bilibiliQrPoll).toHaveBeenLastCalledWith('current')
})

it('shows actionable upstream errors while checking an existing QR session',async()=>{
 vi.mocked(bilibiliQrGenerate).mockResolvedValue({qr_url:'https://passport.bilibili.com/current',qrcode_key:'current'})
 vi.mocked(bilibiliQrPoll).mockRejectedValue(new Error('Bilibili restricted QR login requests. Use cookie import.'))
 await mount();await act(async()=>button('Generate QR Code').click())
 await act(async()=>vi.advanceTimersByTimeAsync(2100))
 expect(node.textContent).toContain('Bilibili restricted QR login requests. Use cookie import.')
})
