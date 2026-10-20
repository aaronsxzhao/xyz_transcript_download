import { useEffect, useState } from 'react'
import { applyWebsiteUpdate, hasWebsiteUpdate } from '../lib/publicCache'

export default function WebsiteUpdate() {
  const [available, setAvailable] = useState(hasWebsiteUpdate)
  useEffect(() => {
    const update = () => setAvailable(hasWebsiteUpdate())
    window.addEventListener('xyz:website-update', update)
    update()
    return () => window.removeEventListener('xyz:website-update', update)
  }, [])
  if (!available) return null
  return <div role="status" className="flex flex-wrap items-center justify-center gap-3 bg-indigo-950 border-t border-indigo-500/40 px-4 py-3 text-sm text-indigo-100">
    <span>Website update ready. Save any edits, then reload to use the latest version.</span>
    <button onClick={applyWebsiteUpdate} className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500">Reload</button>
  </div>
}
