import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { useStore } from "../lib/store";
import UploadSessionItem from "./UploadSessionItem";
import { useDialog } from "../lib/reading";
import type { ContentUpdates } from "../lib/api";
export default function DashboardDialog({
  kind,
  updates,
  history,
  onClose,
}: {
  kind: "updates" | "history";
  updates: ContentUpdates["items"];
  history: ReactNode;
  onClose: () => void;
}) {
  const dialogRef = useDialog(true, onClose);
  const { uploadSessions, videoTasks, removeUploadSession, wsConnected } = useStore();
  const uploads = uploadSessions.filter(s => !s.taskId || !videoTasks.some(t => t.id === s.taskId));
  useEffect(() => {
    if (kind === "history") window.dispatchEvent(new Event("xyz:processing-changed"));
  }, [kind]);
  return (
    <div className="reader-confirm-backdrop" onClick={onClose}>
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={kind === "updates" ? "New content" : "Task history"}
        className="dashboard-dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <h2>{kind === "updates" ? "New content" : "Task history"}</h2>
          <button
            className="reader-action reader-action-icon"
            aria-label="Close dashboard dialog"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        {kind === "updates" ? (
          <ul>
            {updates.map((item) => (
              <li key={item.item_key}>
                <Link
                  to={
                    item.kind === "podcast"
                      ? `/podcasts/${encodeURIComponent(item.source_id)}/episodes`
                      : `/videos/${encodeURIComponent(item.source_id)}`
                  }
                >
                  <span>{item.source_title}</span>
                  <strong>{item.title || "New video"}</strong>
                </Link>
              </li>
            ))}
            {!updates.length && <li>All caught up.</li>}
          </ul>
        ) : (
          <div className="dashboard-task-history">
            {!wsConnected && <p role="status" className="text-sm text-gray-400">Live updates reconnecting. Checking progress automatically.</p>}
            {uploads.map(session => <UploadSessionItem key={session.id} session={session} onDismiss={() => removeUploadSession(session.id)} />)}
            {history || (!uploads.length && <p>No recent tasks. Add a podcast or video to get started.</p>)}
          </div>
        )}
      </section>
    </div>
  );
}
