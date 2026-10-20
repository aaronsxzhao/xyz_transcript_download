import { useEffect, useRef, useState } from 'react'
import { ZoomIn, ZoomOut, Maximize, Download, Loader2, RotateCcw } from 'lucide-react'
import type { Markmap } from 'markmap-view'

// The no-plugins transformer renders Markdown locally without pulling KaTeX,
// syntax highlighters or scripts from a CDN when the user opens the map.
export const preloadMindMap = () => Promise.all([import('markmap-lib/no-plugins'), import('markmap-view')])

export default function MindMapView({ markdown }: { markdown: string }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const instance = useRef<Markmap | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    let map: Markmap | undefined
    let observer: ResizeObserver | undefined
    setLoading(true); setError('')
    async function init() {
      try {
        const [{ Transformer }, { Markmap }] = await preloadMindMap()
        if (cancelled || !svgRef.current || !containerRef.current) return
        const transformer = new Transformer([])
        transformer.md.set({ html: false })
        // Screenshots remain in the note; avoid downloading them all again as
        // SVG foreignObjects, which also makes maps enormous and hard to read.
        transformer.md.renderer.rules.image = () => ''
        const { root } = transformer.transform(markdown || '# No note content yet')
        svgRef.current.replaceChildren()
        map = Markmap.create(svgRef.current, { autoFit: false, duration: 0, maxWidth: 320, initialExpandLevel: 2, fitRatio: 0.9 }, root)
        instance.current = map
        await map.fit()
        if (cancelled) return
        setLoading(false)
        observer = new ResizeObserver(entries => {
          if (entries[0]?.contentRect.width && entries[0]?.contentRect.height) void map?.fit()
        })
        observer.observe(containerRef.current)
      } catch {
        if (!cancelled) { setError('The mind map could not load. Your note is still available.'); setLoading(false) }
      }
    }
    void init()
    return () => { cancelled = true; observer?.disconnect(); map?.destroy(); instance.current = null }
  }, [markdown, attempt])

  function exportSVG() {
    if (!svgRef.current) return
    const clone = svgRef.current.cloneNode(true) as SVGSVGElement
    const box = svgRef.current.getBoundingClientRect()
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    clone.setAttribute('width', String(Math.round(box.width)))
    clone.setAttribute('height', String(Math.round(box.height)))
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }))
    const a = document.createElement('a'); a.href = url; a.download = 'mindmap.svg'; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <div ref={containerRef} className="mindmap-canvas relative w-full" aria-busy={loading}>
    <div className="absolute top-2 left-2 z-10 text-xs text-gray-400 pointer-events-none">Drag to move · Scroll to zoom · Click a branch to expand</div>
    <div className="absolute top-10 sm:top-2 right-2 z-10 flex gap-1 bg-dark-surface rounded-lg border border-dark-border p-1">
      <button disabled={loading || !!error} aria-label="Zoom in" onClick={() => void instance.current?.rescale(1.25)} className="p-2 disabled:opacity-40"><ZoomIn size={18} /></button>
      <button disabled={loading || !!error} aria-label="Zoom out" onClick={() => void instance.current?.rescale(0.8)} className="p-2 disabled:opacity-40"><ZoomOut size={18} /></button>
      <button disabled={loading || !!error} aria-label="Fit to view" onClick={() => void instance.current?.fit()} className="p-2 disabled:opacity-40"><Maximize size={18} /></button>
      <button disabled={loading || !!error} aria-label="Export SVG" onClick={exportSVG} className="p-2 disabled:opacity-40"><Download size={18} /></button>
    </div>
    {loading && <div role="status" className="absolute inset-0 flex items-center justify-center gap-3"><Loader2 className="animate-spin" size={22} />Building mind map…</div>}
    {error && <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center"><p>{error}</p><button className="flex gap-2 items-center px-4 py-2 border border-dark-border rounded-lg" onClick={() => setAttempt(v => v + 1)}><RotateCcw size={16} />Retry mind map</button></div>}
    <svg ref={svgRef} className="w-full h-full min-h-[460px]" aria-label="Interactive mind map" />
  </div>
}
