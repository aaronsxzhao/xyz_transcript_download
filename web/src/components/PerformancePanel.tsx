import { useState } from 'react'
import { authFetch } from '../lib/api'

type Timing = {samples:number; p50_ms:number; p95_ms:number; slow_count:number; error_count:number}
export default function PerformancePanel() {
  const [pages,setPages]=useState<Record<string,Timing>|null>(null)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const load=async()=>{
    setLoading(true);setError('')
    try {
      const response=await authFetch('/api/performance')
      if(!response.ok) throw new Error('Could not load recent timings. Please retry.')
      setPages((await response.json()).pages)
    } catch(e) {setError(e instanceof Error ? e.message : 'Could not load timings')}
    finally {setLoading(false)}
  }
  const seconds=(value:number)=>Number.isFinite(value) ? `${(value/1000).toFixed(2)}s` : '—'
  return <section className="p-5 bg-dark-surface border border-dark-border rounded-xl space-y-3">
    <h2 className="font-semibold">Loading performance</h2>
    <p className="text-sm text-gray-400">Recent visits from your account, including other devices. “Slow visits” is the 95th percentile; a few samples may not represent your usual speed.</p>
    <button disabled={loading} onClick={()=>void load()} className="px-3 py-2 rounded-lg bg-dark-hover disabled:opacity-50">{loading?'Loading timings…':'Show recent timings'}</button>
    {error&&<p role="alert" className="text-sm text-red-300">{error}</p>}
    {pages&&Object.keys(pages).length===0&&<p className="text-sm text-gray-400">No recorded visits yet. Open a few pages, then check again.</p>}
    {pages&&Object.keys(pages).length>0&&<div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr>{['Page','Typical','Slow visits','Samples','Errors'].map(label=><th className="py-2 pr-3" key={label}>{label}</th>)}</tr></thead><tbody>{Object.entries(pages).map(([page,t])=><tr key={page} className="border-t border-dark-border"><td className="py-2 pr-3 capitalize">{page.replace(/_/g,' ')}</td><td className="pr-3">{seconds(t.p50_ms)}</td><td className="pr-3">{seconds(t.p95_ms)}</td><td>{t.samples}</td><td>{t.error_count}</td></tr>)}</tbody></table></div>}
  </section>
}
