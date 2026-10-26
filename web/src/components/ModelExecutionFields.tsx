import { useEffect, useState } from 'react'
import { authFetch, parseApiResponseAsJson } from '../lib/api'

export type ExecutionOptions = { llm_reasoning_effort: string; llm_service_tier: string }
export default function ModelExecutionFields({provider,model,baseUrl,value,onChange,disabled}:{provider:string;model:string;baseUrl:string;value:ExecutionOptions;onChange:(value:ExecutionOptions)=>void;disabled:boolean}) {
  const [caps,setCaps]=useState<{reasoning:string[];tiers:string[];known:boolean}|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{
    setCaps(null);setError('')
    if(!model)return
    const controller=new AbortController()
    const timer=setTimeout(()=>{
      void Promise.resolve().then(()=>authFetch('/api/settings/model-options',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({llm_provider:provider,llm_model:model,...(provider==='custom'?{llm_base_url:baseUrl}:{})}),signal:controller.signal}))
        .then(r=>parseApiResponseAsJson<{reasoning:string[];tiers:string[];known:boolean}>(r,'Cannot read model options'))
        .then(data=>{if(!controller.signal.aborted)setCaps(data)})
        .catch(()=>{if(!controller.signal.aborted)setError('Cannot read model options. Retry by reselecting the model; saved selections are retained.')})
    },350)
    return()=>{clearTimeout(timer);controller.abort()}
  },[provider,model,baseUrl])
  return <fieldset disabled={disabled} className="space-y-3 min-w-0">
    <legend className="text-sm font-medium mb-2">Model execution</legend>
    <p className="text-xs text-gray-400">{provider==='groq'?'Groq summaries use your existing transcription key and API plan.':provider==='custom'?'Uses your endpoint, key and model. Refresh to list available models.':'Uses the server-configured provider.'} Video frame analysis requires a vision-capable provider.</p>
    {error&&<p role="status" className="text-sm text-amber-300">{error}</p>}
    {([['llm_reasoning_effort','Reasoning effort',caps?.reasoning],['llm_service_tier','Service tier',caps?.tiers]] as const).map(([field,label,options])=><label key={field} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-sm text-gray-400">{label}
      <select aria-label={label} value={value[field]} disabled={disabled||!caps} onChange={event=>onChange({...value,[field]:event.target.value})} className="min-w-0 w-full sm:w-56 rounded-lg border border-dark-border bg-dark-hover px-3 py-2 text-white">
        <option value="">Provider default</option>
        {value[field]&&!options?.includes(value[field])&&<option value={value[field]}>{value[field]} · recheck support</option>}
        {options?.map(option=><option key={option} value={option}>{option}</option>)}
      </select>
    </label>)}
    <p className="text-xs text-gray-400">{caps?.known?'Options documented for this provider and model.':'This endpoint does not publish verified capabilities. Only choose values documented by your provider, then test the configuration.'} Lower reasoning can reduce latency but may change quality. Fast/priority/performance tiers depend on provider access and pricing; flex is not a universal fast mode. These options apply to summaries, not audio transcription.</p>
  </fieldset>
}
