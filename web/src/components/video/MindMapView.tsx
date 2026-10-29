import { useEffect, useRef, useState } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize,
  Download,
  Loader2,
  RotateCcw,
} from "lucide-react";
import type { Markmap } from "markmap-view";
import { prepareMindMap } from "../../lib/mindmapCache";

// Same-origin modules only: opening a map never waits for a third-party CDN.
export const preloadMindMap = () => import("markmap-view");

export default function MindMapView({
  markdown,
  active = true,
}: {
  markdown: string;
  active?: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const instance = useRef<Markmap | null>(null);
  const builtFor = useRef("");
  const activeRef = useRef(active);
  activeRef.current = active;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [limited, setLimited] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const fit = () => {
    if (activeRef.current && containerRef.current?.clientWidth)
      void instance.current?.fit().catch(() => {});
  };

  useEffect(() => {
    if (!active || !markdown.trim()) return;
    if (builtFor.current === markdown && instance.current) {
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    setLoading(true);
    setError("");
    let map: Markmap | undefined;
    async function init() {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const [{ Markmap }, outline] = await Promise.race([
          Promise.all([
            preloadMindMap(),
            prepareMindMap(markdown, abort.signal),
          ]),
          new Promise<never>((_, reject) => {
            timer = setTimeout(
              () => reject(new Error("Mind map loading timed out")),
              15000,
            );
          }),
        ]);
        if (abort.signal.aborted || !svgRef.current || !containerRef.current)
          return;
        instance.current?.destroy();
        instance.current = null;
        svgRef.current.replaceChildren();
        map = Markmap.create(
          svgRef.current,
          {
            autoFit: false,
            duration: 0,
            maxWidth: 300,
            initialExpandLevel: 2,
            fitRatio: 0.88,
          },
          outline.root,
        );
        instance.current = map;
        builtFor.current = markdown;
        setLimited(outline.limited);
        await map.fit();
        if (!abort.signal.aborted) setLoading(false);
      } catch {
        if (!abort.signal.aborted) {
          builtFor.current = "";
          map?.destroy();
          if (instance.current === map) instance.current = null;
          setError(
            "The mind map could not load. Your summary is still available.",
          );
          setLoading(false);
          abort.abort();
        }
      } finally {
        clearTimeout(timer);
      }
    }
    void init();
    return () => abort.abort();
  }, [markdown, active, attempt]);

  useEffect(() => {
    if (!active) return;
    let frame = 0,
      lastWidth = 0,
      lastHeight = 0;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (!width || !height || (width === lastWidth && height === lastHeight))
        return;
      lastWidth = width;
      lastHeight = height;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    });
    if (containerRef.current) observer.observe(containerRef.current);
    frame = requestAnimationFrame(fit);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [active]);
  useEffect(
    () => () => {
      instance.current?.destroy();
      instance.current = null;
    },
    [],
  );

  function exportSVG() {
    if (!svgRef.current || loading || error) return;
    const clone = svgRef.current.cloneNode(true) as SVGSVGElement,
      box = svgRef.current.getBoundingClientRect();
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(Math.round(box.width)));
    clone.setAttribute("height", String(Math.round(box.height)));
    const style = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "style",
    );
    const foreground = getComputedStyle(svgRef.current).color;
    const background = containerRef.current ? getComputedStyle(containerRef.current).backgroundColor : "#0f172a";
    style.textContent =
      `.markmap-foreign{font:14px/1.5 sans-serif;color:${foreground}}.markmap-foreign a{color:inherit}.markmap-foreign div{white-space:normal}.markmap-link{fill:none}.markmap-node{cursor:pointer}`;
    clone.prepend(style);
    clone.style.background = background;
    const url = URL.createObjectURL(
      new Blob([new XMLSerializer().serializeToString(clone)], {
        type: "image/svg+xml",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "mindmap.svg";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  if (!markdown.trim())
    return (
      <div className="ui-empty-state">
        <h2>No summary to map yet</h2>
        <p>The mind map becomes available after a summary is saved.</p>
      </div>
    );
  return (
    <div className="mindmap-view">
      <div className="mindmap-heading">
        <p>Drag to move · Scroll to zoom · Click a branch to expand</p>
        <div className="mindmap-actions">
          <button
            disabled={loading || !!error}
            aria-label="Zoom in"
            onClick={() => void instance.current?.rescale(1.25)}
          >
            <ZoomIn size={17} />
          </button>
          <button
            disabled={loading || !!error}
            aria-label="Zoom out"
            onClick={() => void instance.current?.rescale(0.8)}
          >
            <ZoomOut size={17} />
          </button>
          <button
            disabled={loading || !!error}
            aria-label="Fit to view"
            onClick={fit}
          >
            <Maximize size={17} />
          </button>
          <button
            disabled={loading || !!error}
            aria-label="Export SVG"
            onClick={exportSVG}
          >
            <Download size={17} />
          </button>
        </div>
      </div>
      <div ref={containerRef} className="mindmap-canvas" aria-busy={loading}>
        {loading && (
          <div role="status" className="mindmap-overlay">
            <Loader2 className="animate-spin" size={22} />
            Preparing mind map…
          </div>
        )}
        {error && (
          <div role="alert" className="mindmap-overlay">
            <p>{error}</p>
            <button
              className="reader-action reader-action-outlined"
              onClick={() => {
                builtFor.current = "";
                setAttempt((value) => value + 1);
              }}
            >
              <RotateCcw size={16} />
              Retry mind map
            </button>
          </div>
        )}
        <svg
          ref={svgRef}
          className="w-full h-full"
          aria-label="Interactive mind map"
        />
      </div>
      <p className="mindmap-caption">
        Chapter outline
        {limited ? " · Long labels and branches are shortened" : ""}. Read the
        Summary for complete details.
      </p>
    </div>
  );
}
