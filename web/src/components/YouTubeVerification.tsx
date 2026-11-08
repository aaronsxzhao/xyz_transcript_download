import {useEffect, useRef, useState} from 'react'
import {authFetch, parseApiResponseAsJson} from '../lib/api'
import {requestWithDeadline} from '../lib/requestDeadline'

type Report = {reference:string; checked_at:string; revision:string; cookie_present:boolean; metadata_ok:boolean; download_ok:boolean; sample_bytes:number; elapsed_seconds:number; stage:string; code:string; message:string; runtime:Record<string,string|boolean>}
export default function YouTubeVerification({disabled=false}:{disabled?:boolean}) {
 const [url,setUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[report,setReport]=useState<Report|null>(null),[copied,setCopied]=useState(false)
 const request=useRef<AbortController>()
 useEffect(()=>{
  const reset=()=>{request.current?.abort();setBusy(false);setReport(null);setError('');setUrl('');setCopied(false)}
  window.addEventListener('xyz:session-changed',reset)
  return()=>{request.current?.abort();window.removeEventListener('xyz:session-changed',reset)}
 },[])
 useEffect(()=>{if(disabled){request.current?.abort();setBusy(false);setReport(null);setError('');setCopied(false)}},[disabled])
 async function verify(){
  if(busy)return
  const controller=new AbortController();request.current=controller
  setBusy(true);setError('');setReport(null);setCopied(false)
  try{
   const result=await requestWithDeadline(async signal=>{
    const response=await authFetch('/api/cookies/youtube/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video_url:url}),signal})
    return parseApiResponseAsJson<Report>(response,'Could not verify YouTube')
   },{signal:controller.signal,timeout:55000,retry:false})
   if(!controller.signal.aborted)setReport(result)
  }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Verification failed')}
  finally{if(!controller.signal.aborted)setBusy(false)}
 }
 async function copy(){
  if(!report)return
  try{await navigator.clipboard.writeText(JSON.stringify(report,null,2));setCopied(true)}
  catch{setError('Could not copy the report. The diagnostic reference is shown below.')}
 }
 return <section className="p-3 border border-dark-border rounded-lg space-y-3" aria-label="YouTube verification">
  <h3 className="font-medium text-white">Verify YouTube</h3>
  <p className="text-sm text-gray-400">Test the saved cookies from this server by reading video information and downloading up to 64 KiB of media. No summary is generated.</p>
  <label className="block text-sm text-gray-300">YouTube video URL (optional)
   <input type="url" value={url} onChange={event=>{setUrl(event.target.value);setReport(null);setCopied(false)}} disabled={busy} placeholder="Leave blank to use a public test video" className="mt-1 w-full min-w-0 bg-dark-hover border border-dark-border rounded-lg p-2 text-white" />
  </label>
  <button type="button" className="ui-button ui-button-primary" disabled={busy||disabled} onClick={()=>void verify()}>{busy?'Verifying…':'Verify connection and download'}</button>
  {busy&&<p role="status" className="text-sm text-gray-400">Checking from the server. This can take up to 45 seconds.</p>}
  {error&&<p role="alert" className="text-sm text-red-400">{error}</p>}
  {report&&<div role="status" className="space-y-2 text-sm text-gray-300">
   <p className={report.code==='ok'?'text-green-400':'text-amber-400'}>{report.message}</p>
   <ul className="space-y-1"><li>Saved cookies: {report.code==='storage_unavailable'?'unknown (storage unavailable)':report.cookie_present?'found':'missing'}</li><li>Video information: {report.metadata_ok?'passed':'not verified'}</li><li>Media sample: {report.download_ok?`passed (${report.sample_bytes} bytes)`:'not verified'}</li></ul>
   <p className="text-xs text-gray-400">A public-video check confirms access for that video; it does not prove that all account-only videos are accessible.</p>
   <p className="text-xs text-gray-400 break-all">Reference: {report.reference} · {report.elapsed_seconds}s</p>
   <button type="button" className="ui-button" onClick={()=>void copy()}>{copied?'Copied':'Copy diagnostic report'}</button>
  </div>}
 </section>
}
