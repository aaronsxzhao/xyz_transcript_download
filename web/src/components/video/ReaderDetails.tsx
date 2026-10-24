import { lazy, useEffect, useRef } from "react";
import { ExternalLink, X } from "lucide-react";
import { OptionalTool } from "../DeferredView";
import type { VideoTask } from "../../lib/api";
const NoteRecovery = lazy(() =>
  import("../DataRecovery").then((module) => ({
    default: module.NoteRecovery,
  })),
);
export default function ReaderDetails({
  kind,
  task,
  selectedVersion,
  onVersion,
  onClose,
  onRestored,
}: {
  kind: string;
  task: VideoTask;
  selectedVersion: string;
  onVersion: (id: string) => void;
  onClose: () => void;
  onRestored: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (kind !== 'recovery') return;
    panel.current?.focus({preventScroll:true});
    panel.current?.scrollIntoView({block:'start'});
  }, [kind]);
  const versions = task.versions || [];
  const original = task.style === 'original' && ['twitter', 'substack'].includes(task.platform);
  const duration = `${Math.floor(task.duration / 60)}:${String(Math.floor(task.duration % 60)).padStart(2, "0")}`;
  return (
    <section
      ref={panel}
      tabIndex={-1}
      className="reader-utility-panel"
      aria-label={
        kind === "versions"
          ? "Version history"
          : kind === "source"
            ? "Source details"
            : "Screenshot recovery"
      }
    >
      <button
        className="reader-action reader-utility-close"
        aria-label="Close details"
        onClick={onClose}
      >
        <X size={16} />
      </button>
      {kind === "source" && (
        <>
          <h2>Source details</h2>
          <dl>
            <dt>Platform</dt>
            <dd>{task.platform}</dd>
            {task.duration > 0 && <><dt>Duration</dt><dd>{duration}</dd></>}
            <dt>Model</dt>
            <dd>{original ? "No AI used · original text" : task.model || "Not recorded"}</dd>
            <dt>Formats</dt>
            <dd>{task.formats?.join(", ") || "Summary"}</dd>
          </dl>
          {task.platform !== "local" && /^https?:\/\//.test(task.url) && (
            <a
              href={task.url}
              target="_blank"
              rel="noopener noreferrer"
              className="reader-action"
            >
              <ExternalLink size={16} />
              Open source
            </a>
          )}
        </>
      )}
      {kind === "versions" && (
        <>
          <h2>Version history</h2>
          <label>
            Note version{" "}
            <select
              aria-label="Note version"
              value={selectedVersion}
              onChange={(event) => onVersion(event.target.value)}
            >
              <option value="">Latest</option>
              {versions.map((version, index) => (
                <option key={version.id} value={version.id}>
                  v{versions.length - index} · {version.style || "default"}
                  {version.created_at
                    ? ` · ${new Date(version.created_at).toLocaleDateString()}`
                    : ""}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {kind === "recovery" && (
        <OptionalTool fallback={<p role="status">Loading recovery tools…</p>}>
          <NoteRecovery
            expanded
            onRestored={onRestored}
            id={task.id}
            version={selectedVersion}
            warning={task.status === "success" ? task.error : ""}
            failed={task.status === "failed"}
            local={task.platform === "local"}
          />
        </OptionalTool>
      )}
    </section>
  );
}
