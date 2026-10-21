import { useState, useEffect, type ReactNode } from 'react'
import { getPreference, setPreference } from '../lib/preferences'

export default function ReaderControls({children}: {children?: ReactNode}) {
  const [options,setOptions]=useState(false)
  const [size, setSize] = useState(() => Math.max(14, Math.min(22, Number(getPreference('reader_font_size') || 16))))
  const [width, setWidth] = useState(() => getPreference('reader_width') || 'comfortable')
  const [contents, setContents] = useState(() => getPreference('reader_contents') !== 'hidden')
  useEffect(() => {
    document.documentElement.dataset.readerWidth = width
    document.documentElement.dataset.readerContents = contents ? 'visible' : 'hidden'
    setPreference('reader_width', width); setPreference('reader_contents', contents ? 'visible' : 'hidden')
  }, [width, contents])
  useEffect(() => { document.documentElement.style.setProperty('--reader-font-size', `${size}px`); setPreference('reader_font_size', String(size)) }, [size])
  return <div className="reader-controls" aria-label="Reading text size">
    <button className="reader-options-toggle" aria-expanded={options} aria-controls="reader-text-options" onClick={()=>setOptions(value=>!value)}>Reading options</button>
    <div id="reader-text-options" className="reader-text-options" data-expanded={options}>
    <button disabled={size <= 14} aria-label="Smaller reading text" onClick={() => setSize(s => Math.max(14, s - 1))} className="px-3 py-2 rounded bg-dark-surface border border-dark-border">A−</button>
    <button disabled={size >= 22} aria-label="Larger reading text" onClick={() => setSize(s => Math.min(22, s + 1))} className="px-3 py-2 rounded bg-dark-surface border border-dark-border">A+</button>
    <select aria-label="Reading width" value={width} onChange={e => setWidth(e.target.value)} className="px-3 py-2 rounded bg-dark-surface border border-dark-border"><option value="comfortable">Comfortable</option><option value="wide">Wide</option></select>
    <button aria-pressed={contents} onClick={() => setContents(value => !value)} className="px-3 py-2 rounded bg-dark-surface border border-dark-border">{contents ? 'Hide contents' : 'Show contents'}</button>
    </div>
    {children}
  </div>
}
