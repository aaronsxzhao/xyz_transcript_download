import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ChevronDown,
  MoreHorizontal,
  RefreshCw,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { deferView } from "./DeferredView";
const RegenerateDialog = deferView(() => import("./RegenerateDialog"));
import ReaderControls from "./ReaderControls";

export type ReaderSection = { id: string; title: string; level?: number };

/** A non-modal disclosure: Tab follows the page; Escape returns to its trigger. */
export function ReaderMenu({
  label,
  icon,
  children,
  outlined = false,
  iconOnly = false,
  busy = false,
}: {
  label: string;
  icon: ReactNode;
  children: ReactNode;
  outlined?: boolean;
  iconOnly?: boolean;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div
      ref={ref}
      className="reader-menu"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setOpen(false);
      }}
    >
      <button
        ref={trigger}
        className={`reader-action ${outlined ? "reader-action-outlined" : ""} ${iconOnly ? "reader-action-icon" : ""}`}
        title={label}
        aria-label={label}
        aria-busy={busy}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((value) => !value)}
      >
        {icon}
        {!iconOnly && <span>{label}</span>}
        {outlined && <ChevronDown size={12} />}
      </button>
      {open && (
        <div
          id={id}
          className="reader-menu-panel"
          aria-label={label}
          onClick={(event) => {
            if (
              (event.target as HTMLElement).closest("button,a") &&
              !(event.target as HTMLElement).closest("[data-keep-open]")
            )
              setOpen(false);
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function RegenerateAction({
  onConfirm,
  disabled,
  busy,
  description = "Rebuild the summary from the saved transcript.",
}: {
  onConfirm: () => void;
  disabled?: boolean;
  busy?: boolean;
  description?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        disabled={disabled || busy}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        <RefreshCw size={16} className={busy ? "animate-spin" : ""} />
        {busy ? "Regenerating…" : "Regenerate summary"}
      </button>
      {open && (
        <RegenerateDialog
          description={description}
          onClose={() => setOpen(false)}
          onConfirm={onConfirm}
          fallback={<p role="status">Loading confirmation…</p>}
        />
      )}
    </>
  );
}

export function MoreReaderActions({ children }: { children: ReactNode }) {
  return (
    <ReaderMenu
      label="More summary actions"
      icon={<MoreHorizontal size={17} />}
      iconOnly
    >
      {children}
    </ReaderMenu>
  );
}

export default function ReaderFrame({
  title,
  kind,
  metadata,
  actions,
  tabs,
  sections,
  activeSection,
  onNavigate,
  children,
}: {
  title: string;
  kind: "Podcast" | "Video";
  metadata?: ReactNode;
  actions: ReactNode;
  tabs: ReactNode;
  sections: ReaderSection[];
  activeSection?: string;
  onNavigate: (id: string) => void;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const [visibleSection, setVisibleSection] = useState("");
  const ids = sections.map((section) => section.id).join("\n");
  useEffect(() => {
    if (!ids) return;
    const observed = new WeakSet<Element>();
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setVisibleSection(visible[0].target.id);
      },
      {
        root: document.querySelector("main"),
        rootMargin: "-64px 0px -60% 0px",
      },
    );
    const scan = () =>
      ids.split("\n").forEach((id) => {
        const element = document.getElementById(id);
        if (element && !observed.has(element)) {
          observed.add(element);
          observer.observe(element);
        }
      });
    scan();
    const changes = new MutationObserver(scan);
    const documentBody = document.querySelector(".unified-document");
    if (documentBody)
      changes.observe(documentBody, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      changes.disconnect();
    };
  }, [ids]);
  return (
    <div className="unified-reader" data-outline={!!sections.length}>
      <aside
        className="unified-outline"
        data-reader-contents
        aria-label="Reading outline"
      >
        <h2>Contents</h2>
        <nav>
          {sections.map((section) => (
            <button
              key={section.id}
              aria-current={
                (activeSection || visibleSection) === section.id
                  ? "location"
                  : undefined
              }
              onClick={() => onNavigate(section.id)}
              style={{
                paddingLeft: section.level && section.level > 2 ? 18 : 10,
              }}
            >
              {section.title}
            </button>
          ))}
        </nav>
      </aside>
      <div className="unified-document">
        <header className="unified-header">
          <div className="reader-breadcrumb">
            <button onClick={() => navigate(-1)} aria-label="Go back">
              <ArrowLeft size={14} /> Back
            </button>
            <span>/</span>
            <span>{kind} summary</span>
          </div>
          <h1>{title}</h1>
          <div className="reader-metadata-row">
            <div className="reader-metadata">{metadata}</div>
            <div
              className="unified-actions"
              role="group"
              aria-label="Note actions"
            >
              {actions}
            </div>
          </div>
        </header>
        <div className="unified-toolbar">
          <div
            className="unified-tabs"
            role="tablist"
            aria-label="Reading view"
            onKeyDown={(event) => {
              if (
                !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              )
                return;
              const tabs = Array.from(
                event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  '[role="tab"]',
                ),
              );
              const index = tabs.indexOf(
                document.activeElement as HTMLButtonElement,
              );
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? tabs.length - 1
                    : (index +
                        (event.key === "ArrowRight" ? 1 : -1) +
                        tabs.length) %
                      tabs.length;
              event.preventDefault();
              tabs[next]?.focus();
              tabs[next]?.click();
            }}
          >
            {tabs}
          </div>
          <ReaderControls
            sections={sections}
            onNavigate={onNavigate}
            activeSection={activeSection || visibleSection}
          />
        </div>
        {children}
      </div>
    </div>
  );
}
