import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { Activity, X } from "lucide-react";
import { useStore } from "../lib/store";

import {
  cancelTask,
  retryTask,
  dismissTask,
  dismissedTasks,
} from "../lib/taskActions";
import { useDialog } from "../lib/reading";
import ProcessingProgress from "./ProcessingProgress";
import { taskVisible } from "../lib/taskPreferences";
import { taskGroup } from "./TaskStatus";
import UploadSessionItem from "./UploadSessionItem";
export default function ProcessingPanel() {
  const state = useStore();
  const { pathname, key: locationKey } = useLocation();
  const [open, setOpen] = useState(false);
  // Reveal the destination even when a task link opens the current route again.
  useEffect(() => setOpen(false), [locationKey]);
  const [, setDismissed] = useState<string[]>(dismissedTasks);
  useEffect(() => {
    const sync = () => setDismissed(dismissedTasks());
    window.addEventListener("xyz:tasks-dismissed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("xyz:tasks-dismissed", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  const dialogRef = useDialog(open, () => setOpen(false));
  const rows = [
    ...state.jobs.map((job) => ({ ...job, kind: "podcast" as const, platform: '', sourceUrl: '', createdAt: '', task_dismissed: undefined as boolean | undefined })),
    ...state.videoTasks
      .filter((t) => t.status !== "discovered")
      .map((t) => ({
        job_id: t.id,
        task_dismissed: t.task_dismissed,
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
  ].filter(row => taskVisible(row.status, row.kind + ":" + row.job_id, row.task_dismissed));
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
      {(running + queued + failures > 0) && <button
        className="task-launcher"
        aria-label="Open processing tasks"
        aria-haspopup="dialog"
        onClick={() => { setOpen(true); window.dispatchEvent(new Event("xyz:processing-changed")); }}
      >
        <Activity size={16} />
        <span>{count}</span>
      </button>}
      {open &&
        createPortal(
          <div
            className="task-drawer-backdrop ui-scope"
            onClick={() => setOpen(false)}
          >
            <section
              ref={dialogRef}
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
