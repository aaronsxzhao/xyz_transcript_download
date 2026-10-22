import { useState, useEffect } from "react";
import { deferView } from "./DeferredView";
const ReaderAppearance = deferView(() => import("./ReaderAppearance"));
import { List } from "lucide-react";
import { getPreference, setPreference } from "../lib/preferences";
import { ReaderMenu, type ReaderSection } from "./ReaderChrome";

export default function ReaderControls({
  sections = [],
  onNavigate,
  activeSection,
}: {
  sections?: ReaderSection[];
  onNavigate?: (id: string) => void;
  activeSection?: string;
}) {
  const [size, setSize] = useState(() => {
    const value = Number(getPreference("reader_font_size") || 16);
    return Number.isFinite(value) ? Math.max(14, Math.min(22, value)) : 16;
  });
  const [width, setWidth] = useState(() =>
    getPreference("reader_width") === "wide" ? "wide" : "comfortable",
  );
  const [contents, setContents] = useState(
    () => getPreference("reader_contents") !== "hidden",
  );
  useEffect(() => {
    document.documentElement.dataset.readerWidth = width;
    document.documentElement.dataset.readerContents = contents
      ? "visible"
      : "hidden";
    setPreference("reader_width", width);
    setPreference("reader_contents", contents ? "visible" : "hidden");
  }, [width, contents]);
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--reader-font-size",
      `${size}px`,
    );
    setPreference("reader_font_size", String(size));
  }, [size]);
  return (
    <div className="unified-utilities">
      {!!sections.length && (
        <>
          <button
            className="reader-action desktop-contents"
            aria-label="Toggle contents"
            aria-pressed={contents}
            onClick={() => setContents((value) => !value)}
          >
            <List size={16} />
            <span>Contents</span>
          </button>
          <div className="mobile-contents">
            <ReaderMenu label="Contents" icon={<List size={16} />}>
              {sections.map((section) => (
                <button
                  key={section.id}
                  aria-current={
                    section.id === activeSection ? "location" : undefined
                  }
                  onClick={() => onNavigate?.(section.id)}
                >
                  {section.title}
                </button>
              ))}
            </ReaderMenu>
          </div>
        </>
      )}
      <ReaderMenu
        label="Reading appearance"
        icon={<span className="reader-aa">Aa</span>}
      >
        <ReaderAppearance
          size={size}
          width={width}
          onSize={setSize}
          onWidth={setWidth}
          fallback={<p role="status">Loading appearance…</p>}
        />
      </ReaderMenu>
    </div>
  );
}
