import { useEffect, useRef, useState } from 'react'
import { ZoomIn, ZoomOut, Maximize, Download } from 'lucide-react'

interface Props {
  markdown: string
}

export default function MindMapView({ markdown }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [mm, setMm] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function initMindMap() {
      try {
        const { Transformer } = await import('markmap-lib')
        const { Markmap } = await import('markmap-view')

        if (cancelled || !svgRef.current) return

        const transformer = new Transformer()
        const { root } = transformer.transform(markdown)

        svgRef.current.innerHTML = ''

        const mindmap = Markmap.create(svgRef.current, {
          autoFit: true,
          duration: 300,
        }, root)

        setMm(mindmap)
      } catch (e) {
        console.error('Mind map error:', e)
        setError('Failed to load mind map')
      }
    }

    if (markdown) {
      initMindMap()
    }

    return () => {
      cancelled = true
    }
  }, [markdown])

  const handleZoomIn = () => {
    // Markmap doesn't expose zoom directly, but we can use the SVG transform
    if (svgRef.current) {
      const g = svgRef.current.querySelector('g')
      if (g) {
        const current = g.getAttribute('transform') || ''
        const scaleMatch = current.match(/scale\(([^)]+)\)/)
        const currentScale = scaleMatch ? parseFloat(scaleMatch[1]) : 1
        g.setAttribute('transform', current.replace(/scale\([^)]+\)/, `scale(${currentScale * 1.2})`))
      }
    }
  }

  const handleZoomOut = () => {
    if (svgRef.current) {
      const g = svgRef.current.querySelector('g')
      if (g) {
        const current = g.getAttribute('transform') || ''
        const scaleMatch = current.match(/scale\(([^)]+)\)/)
        const currentScale = scaleMatch ? parseFloat(scaleMatch[1]) : 1
        g.setAttribute('transform', current.replace(/scale\([^)]+\)/, `scale(${currentScale * 0.8})`))
      }
    }
  }

  const handleFit = () => {
    mm?.fit()
  }

  const handleExportSVG = () => {
    if (!svgRef.current) return
    const svgData = new XMLSerializer().serializeToString(svgRef.current)
    const blob = new Blob([svgData], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mindmap.svg'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <p>{error}</p>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative h-full w-full">
      {/* Toolbar */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1 bg-dark-surface/90 rounded-lg border border-dark-border p-1">
        <button
          onClick={handleZoomIn}
          className="p-1.5 text-gray-400 hover:text-white transition-colors"
          title="Zoom In"
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 text-gray-400 hover:text-white transition-colors"
          title="Zoom Out"
        >
          <ZoomOut size={16} />
        </button>
        <button
          onClick={handleFit}
          className="p-1.5 text-gray-400 hover:text-white transition-colors"
          title="Fit to View"
        >
          <Maximize size={16} />
        </button>
        <div className="w-px h-5 bg-dark-border mx-0.5" />
        <button
          onClick={handleExportSVG}
          className="p-1.5 text-gray-400 hover:text-white transition-colors"
          title="Export SVG"
        >
          <Download size={16} />
        </button>
      </div>

      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ minHeight: '400px' }}
      />
    </div>
  )
}
