import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { Activity, X, Upload } from "lucide-react";
import { useStore, type VideoUploadSession } from "../lib/store";

import {
  cancelTask,
  retryTask,
  dismissTask,
  dismissedTasks,
} from "../lib/taskActions";
import { useDialog } from "../lib/reading";
import ProcessingProgress from "./ProcessingProgress";
import { taskGroup } from "./TaskStatus";
const formatBytes = (n: number) =>
  `${(Math.max(0, n) / 1048576).toFixed(1)} MB`;
export default function ProcessingPanel() {
  const state = useStore();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState<string[]>(dismissedTasks);
  useEffect(() => {
    const sync = () => setDismissed(dismissedTasks());
    window.addEventListener("xyz:tasks-dismissed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("xyz:tasks-dismissed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  useDialog(open, () => setOpen(false));
  const rows = [
    ...state.jobs.map((job) => ({ ...job, kind: "podcast" as const, platform: '', sourceUrl: '', createdAt: '' })),
    ...state.videoTasks
      .filter((t) => t.status !== "discovered")
      .map((t) => ({
        job_id: t.id,
        episode_title: t.title,
        episode_id: "",
        status: t.status,
        progress: t.progress,
        started_at: t.started_at,
        message: t.error || t.message,
        platform: t.platform,
        sourceUrl: t.url,
        createdAt: t.created_at,
        kind: "video" as const,
      })),
  ].filter(
    (row) =>
      !dismissed.includes(row.kind + ":" + row.job_id) ||
      [
        "pending",
        "parsing",
        "fetching",
        "downloading",
        "transcribing",
        "summarizing",
        "saving",
        "cancelling",
      ].includes(row.status),
  );
  const uploads = state.uploadSessions.filter(
    (s) => !s.taskId || !state.videoTasks.some((t) => t.id === s.taskId),
  );
  const running =
    rows.filter((r) => taskGroup(r.status) === "Processing").length +
    uploads.filter(
      (s) => !["queued", "failed", "success", "cancelled"].includes(s.phase),
    ).length;
  const queued =
    rows.filter((r) => r.status === "pending").length +
    uploads.filter((s) => s.phase === "queued").length;
  const failures =
    rows.filter((r) => r.status === "failed").length +
    uploads.filter((s) => s.phase === "failed").length;
  const count = `${running} processing · ${queued} queued${failures ? ` · ${failures} need attention` : ""}`;
  useEffect(() => {
    if (open && !rows.length && !uploads.length) setOpen(false);
  }, [open, rows.length, uploads.length]);
  if (!rows.length && !uploads.length) return null;
  return (
    <>
      <button
        className="task-launcher"
        aria-label="Open processing tasks"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <Activity size={16} />
        <span>{count}</span>
      </button>
      {open &&
        createPortal(
          <div
            className="task-drawer-backdrop ui-scope"
            onClick={() => setOpen(false)}
          >
            <section
              className="task-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Processing tasks"
              onClick={(e) => e.stopPropagation()}
            >
              <header className="task-drawer-header">
                <div>
                  <h2>Processing tasks</h2>
                  <p className="text-sm text-gray-400">{count}</p>
                </div>
                <button
                  aria-label="Close processing tasks"
                  onClick={() => setOpen(false)}
                >
                  <X size={18} />
                </button>
              </header>
              {!state.wsConnected && (
                <p role="status" className="px-4 py-2 text-sm text-amber-200">
                  Live updates reconnecting. Checking progress automatically.
                </p>
              )}
              <div className="task-drawer-content">
                {uploads.map((session) => (
                  <UploadSessionItem
                    key={session.id}
                    session={session}
                    onDismiss={() => state.removeUploadSession(session.id)}
                  />
                ))}
                {["Processing", "Queued", "Needs attention", "Finished"].map(
                  (group) => {
                    const items = rows.filter(
                      (r) => taskGroup(r.status) === group,
                    );
                    return items.length ? (
                      <section key={group}>
                        <h3 className="task-group-title">
                          {group} · {items.length}
                        </h3>
                        {items.map((job) => (
                          <ProcessingProgress
                            key={job.kind + job.job_id}
                            job={job}
                            kind={job.kind}
                            platform={job.platform}
                            sourceUrl={job.sourceUrl}
                            createdAt={job.createdAt}
                            link={
                              job.kind === "video"
                                ? `/videos/${job.job_id}`
                                : job.episode_id
                                  ? `/viewer/${job.episode_id}`
                                  : undefined
                            }
                            onCancel={() => cancelTask(job, job.kind)}
                            onRetry={() => retryTask(job, job.kind)}
                            onDismiss={() => dismissTask(job, job.kind)}
                          />
                        ))}
                      </section>
                    ) : null;
                  },
                )}
              </div>
              {pathname === "/" && (
                <p className="px-4 py-2 text-xs text-gray-400">
                  Task details are also available in the dashboard queue.
                </p>
              )}
            </section>
          </div>,
          document.body,
        )}
    </>
  );
}
function UploadSessionItem({
  session,
  onDismiss,
}: {
  session: VideoUploadSession;
  onDismiss: () => void;
}) {
  const isActive = !["failed", "success", "cancelled"].includes(session.phase);
  const statusColor =
    session.phase === "failed"
      ? "bg-red-500"
      : session.phase === "success"
        ? "bg-emerald-500"
        : session.phase === "cancelled"
          ? "bg-orange-400"
          : session.phase === "assembling"
            ? "bg-amber-500"
            : session.phase === "uploaded"
              ? "bg-emerald-500"
              : "bg-sky-500";

  return (
    <div className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        <Upload size={16} className="text-sky-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {session.filename || "Uploading local video..."}
          </p>
          <p className="text-xs text-gray-500">
            {session.statusText || session.phase}
          </p>
          <p className="text-[11px] text-gray-600 mt-0.5">
            {session.locationLabel}
          </p>
        </div>
        {!isActive && (
          <button
            onClick={onDismiss}
            className="p-2 sm:p-1 min-w-[40px] min-h-[40px] sm:min-w-0 sm:min-h-0 flex items-center justify-center text-gray-500 hover:text-white hover:bg-dark-border rounded transition-colors -mr-1"
            title="Dismiss"
          >
            <X className="w-5 h-5 sm:w-4 sm:h-4" />
          </button>
        )}
      </div>
      <div className="relative h-1.5 bg-dark-border rounded-full overflow-hidden">
        <div
          className={`absolute left-0 top-0 h-full ${statusColor} transition-all duration-300`}
          style={{ width: `${Math.min(session.percent, 100)}%` }}
        />
        {session.percent === 0 && isActive && (
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
        )}
      </div>
      <div className="flex justify-between items-center">
        <p className="text-xs text-sky-400">
          {formatBytes(session.uploadedBytes)} /{" "}
          {formatBytes(session.totalBytes)}
        </p>
        <p className="text-xs font-medium text-white">
          {Math.round(session.percent)}%
        </p>
      </div>
    </div>
  );
}
