import { useState, useEffect } from 'react'
import { getPreference, setPreference } from '../lib/preferences'

export default function ReaderControls() {
  const [size, setSize] = useState(() => Math.max(14, Math.min(22, Number(getPreference('reader_font_size') || 16))))
  useEffect(() => { document.documentElement.style.setProperty('--reader-font-size', `${size}px`); setPreference('reader_font_size', String(size)) }, [size])
  return <div className="flex items-center gap-1 text-sm" aria-label="Reading text size">
    <button aria-label="Smaller reading text" onClick={() => setSize(s => Math.max(14, s - 1))} className="px-3 py-2 rounded bg-dark-surface border border-dark-border">A−</button>
    <button aria-label="Larger reading text" onClick={() => setSize(s => Math.min(22, s + 1))} className="px-3 py-2 rounded bg-dark-surface border border-dark-border">A+</button>
  </div>
}
