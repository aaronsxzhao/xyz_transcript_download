import Button from "./ui/Button";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Radio, Video } from "lucide-react";
import type { ProcessingJob } from "../lib/api";
import { isActiveStatus } from "../lib/statusUtils";
import { TaskProgress, sourceAction } from "./TaskStatus";
import { useToast } from "./Toast";
export default function ProcessingProgress({
  job,
  link,
  kind,
  onCancel,
  onRetry,
  onDismiss,
}: {
  job: ProcessingJob;
  link?: string;
  kind?: "podcast" | "video";
  onCancel?: (id: string) => Promise<void>;
  onRetry?: (id: string) => Promise<void>;
  onDismiss?: (id: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const { addToast } = useToast();
  const active = isActiveStatus(job.status);
  const restricted = job.status === "failed" && sourceAction(job.message);
  async function action(fn: ((id: string) => Promise<void>) | undefined) {
    if (!fn || locked.current) return;
    locked.current = true;
    setBusy(true);
    try {
      await fn(job.job_id);
    } catch (e) {
      addToast({
        type: "error",
        title: "Task action failed",
        message: e instanceof Error ? e.message : "Please retry.",
      });
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  const Icon = kind === "video" ? Video : Radio;
  return (
    <article
      className={`task-row ${job.status === "failed" ? "task-row-attention" : ""}`}
      data-task-id={job.job_id}
    >
      <div className="flex gap-2 items-start">
        <Icon
          size={16}
          className={kind === "video" ? "text-cyan-400" : "text-indigo-400"}
        />
        <h3 className="task-title">
          {job.episode_title || "Processing content"}
        </h3>
      </div>
      <TaskProgress
        status={restricted ? "restricted" : job.status}
        progress={job.progress}
        startedAt={job.started_at}
      />
      {job.message && <p className="task-message">{job.message}</p>}
      <div className="task-actions">
        {active && job.status !== "cancelling" && onCancel && (
          <Button
            variant="quiet"
            disabled={busy}
            onClick={() => void action(onCancel)}
          >
            {busy ? "Cancelling…" : "Cancel"}
          </Button>
        )}
        {job.status === "failed" && !restricted && onRetry && (
          <Button disabled={busy} onClick={() => void action(onRetry)}>
            {busy ? "Retrying…" : "Retry"}
          </Button>
        )}
        {restricted &&
        job.episode_id &&
        /^[a-f0-9]{24}$/i.test(job.episode_id) ? (
          <a
            className="ui-button"
            target="_blank"
            rel="noopener noreferrer"
            href={`https://www.xiaoyuzhoufm.com/episode/${job.episode_id}`}
          >
            Open original episode
          </a>
        ) : (
          restricted && (
            <Link className="ui-button" to="/settings">
              Check source access
            </Link>
          )
        )}
        {link && ["success", "completed"].includes(job.status) && (
          <Link className="ui-button" to={link}>
            Read summary
          </Link>
        )}
        {!active && onDismiss && (
          <Button
            variant="quiet"
            disabled={busy}
            onClick={() => void action(onDismiss)}
          >
            Dismiss
          </Button>
        )}
      </div>
    </article>
  );
}
