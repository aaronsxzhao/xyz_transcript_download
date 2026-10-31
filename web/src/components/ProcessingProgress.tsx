import Button from "./ui/Button";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Radio, Video } from "lucide-react";
import type { ProcessingJob } from "../lib/api";
import { isActiveStatus } from "../lib/statusUtils";
import { TaskProgress, sourceAction } from "./TaskStatus";
import { useToast } from "./Toast";
import { taskSource, taskFailure } from '../lib/taskSource';
export default function ProcessingProgress({
  job,
  link,
  kind,
  platform,
  sourceUrl,
  createdAt,
  onCancel,
  onRetry,
  onDismiss,
}: {
  job: ProcessingJob;
  link?: string;
  kind?: "podcast" | "video";
  platform?: string;
  sourceUrl?: string;
  createdAt?: string;
  onCancel?: (id: string) => Promise<void>;
  onRetry?: (id: string) => Promise<void>;
  onDismiss?: (id: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const { addToast } = useToast();
  const active = isActiveStatus(job.status);
  const source = taskSource(platform, sourceUrl || job.source_url, job.episode_id, kind);
  const failure = taskFailure(job.message, platform);
  const restricted = job.status === "failed" && (sourceAction(job.message) || failure.retryAfterSignIn);
  const createdValue = createdAt || job.created_at;
  const created = createdValue ? new Date(typeof createdValue === 'number' ? createdValue * 1000 : createdValue) : null;
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
        <div className="min-w-0">
        <h3 className="task-title">
          {job.episode_title || `${source.name} ${kind === 'podcast' ? 'episode' : 'video'} · ${source.id || job.job_id}`}
        </h3>
        <p className="text-xs text-gray-400 mt-1">
        {source.name}
        {created && Number.isFinite(created.getTime()) && <> · Task created <time dateTime={typeof createdValue === 'string' ? createdValue : created.toISOString()}>{created.toLocaleDateString()}</time></>}
        </p>
        </div>
      </div>
      <TaskProgress
        status={restricted ? "restricted" : job.status}
        progress={job.progress}
        startedAt={job.started_at}
        message={failure.message}
      />
      {job.message && !active && <p className="task-message">{failure.message}</p>}
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
        {["failed", "cancelled"].includes(job.status) && (!restricted || failure.retryAfterSignIn) && onRetry && (
          <Button disabled={busy} onClick={() => void action(onRetry)}>
            {busy ? "Retrying…" : "Retry"}
          </Button>
        )}
        {job.status === 'failed' && source.original && (
          <a
            className="ui-button"
            target="_blank"
            rel="noopener noreferrer"
            href={source.original}
          >
            {kind === 'podcast' ? 'Open original episode' : 'Open original video'}
          </a>
        )}
        {restricted && (failure.retryAfterSignIn || !source.original) && (
            <Link className="ui-button" to="/settings">
              {failure.retryAfterSignIn ? `Check ${source.name} account` : 'Check source access'}
            </Link>
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
