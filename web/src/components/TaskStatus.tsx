// Shared processing semantics: queued tasks have no estimated percentage.
import { useState, useEffect } from "react";
import {useSmoothedProgress} from "../lib/smoothedProgress";
import {
  getStatusColor,
  getStatusIcon,
  getStatusText,
  isActiveStatus,
} from "../lib/statusUtils";
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <span className="task-status-badge">
      {getStatusIcon(status)}
      {label || getStatusText(status)}
    </span>
  );
}
export function TaskProgress({
  status,
  progress = 0,
  compact = false,
  startedAt = 0,
  message = "",
  updatedAt,
}: {
  status: string;
  progress?: number;
  compact?: boolean;
  startedAt?: number;
  message?: string;
  updatedAt?: number | string;
}) {
  const [now, setNow] = useState(Date.now());
  const [online, setOnline] = useState(() => navigator.onLine);
  const [lastChange, setLastChange] = useState(Date.now());
  useEffect(() => {
    setLastChange(Date.now());
    setNow(Date.now());
  }, [status, progress, message, startedAt]);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  useEffect(() => {
    if (!isActiveStatus(status) || status === "pending") return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt, status]);
  const elapsed = Math.max(0, Math.floor(now / 1000 - startedAt));
  const incoming = Number.isFinite(progress)
    ? Math.max(0, Math.min(99, Math.round(progress)))
    : 0;
  const complete = status === "completed" || status === "success";
  const value = complete ? 100 : incoming;
  const animated = useSmoothedProgress(value, `${startedAt}:${status === 'pending' ? 'queued' : 'active'}`);
  const waiting = status === "pending" || status === "cancelling";
  const stageMessage = isActiveStatus(status) && !waiting ? message : "";
  const coverageReview = stageMessage.startsWith('Coverage review');
  const stageLabel = status === "summarizing" ? ["Coverage review", "Writing full-transcript summary", "Writing sections", "Checking source accuracy", "Building coverage checklist", "Checking coverage", "Filling missing details", "Verifying additions", "Preparing the final summary"].find(label => stageMessage.startsWith(label)) : undefined;
  const reportedAt = typeof updatedAt === 'string' ? Date.parse(updatedAt) : updatedAt;
  // Old podcast revisions were counters, not epoch timestamps. Never treat
  // those or future/invalid timestamps as evidence of recent backend work.
  const validReport = typeof reportedAt === 'number'
    && reportedAt >= 946684800000 && reportedAt <= now;
  const unchangedSeconds = Math.max(0, Math.floor((now - (validReport ? reportedAt : lastChange)) / 1000));
  const stageHint = coverageReview
    ? "Checking saved transcript sections; your note remains readable."
    : status === "transcribing"
      ? "Audio transcription reports completed batches."
      : "Progress updates when each step finishes.";
  const active = isActiveStatus(status) && !waiting;
  return (
    <div className="task-progress" data-offline={!online || undefined}>
      <div className="task-progress-heading text-xs text-gray-400">
        <StatusBadge status={status} label={stageLabel} />
        {(complete || (isActiveStatus(status) && !waiting && value > 0)) && (
          <span
            className="task-progress-percent"
            title={complete ? "Completed" : "Estimated overall progress"}
          >
            {complete ? "100" : `~${Math.min(99, Math.floor(animated))}`}%
          </span>
        )}
      </div>
      {(complete || (isActiveStatus(status) && !waiting)) && (
        <div
          role={complete ? undefined : "progressbar"}
          aria-hidden={complete || undefined}
          aria-label={stageLabel || getStatusText(status)}
          aria-valuetext={stageMessage ? `${stageMessage}${value > 0 ? `; approximately ${value}% overall` : ""}` : undefined}
          aria-valuemin={0}
          aria-valuemax={100}
          {...(value > 0 ? { "aria-valuenow": value } : {})}
          className="task-progress-track"
        >
          <span
            className={
              value > 0 ? `task-progress-fill ${getStatusColor(status)}` : "task-indeterminate"
            }
            style={value > 0 ? { transform: `scaleX(${complete ? 1 : animated / 100})` } : undefined}
          />
        </div>
      )}
      {stageMessage && <p className="task-stage-message" role="status">{stageMessage}</p>}
      {active && (
        <p className="task-progress-expectation">
          {!online
            ? "You're offline. Reconnect to refresh progress."
            : unchangedSeconds >= 30
              ? `${stageHint} No new progress for ${Math.floor(unchangedSeconds / 60)}m ${unchangedSeconds % 60}s; task activity is unconfirmed.`
              : stageHint}
        </p>
      )}
      {startedAt > 0 && isActiveStatus(status) && status !== "pending" && (
        <span className="text-xs text-gray-500 tabular-nums">
          Elapsed {Math.floor(elapsed / 60)}m {elapsed % 60}s
        </span>
      )}
      {!compact && status === "pending" && (
        <p className="text-xs text-gray-500">
          Waiting for an available processing slot.
        </p>
      )}
    </div>
  );
}
export function taskGroup(status: string) {
  return status === "pending"
    ? "Queued"
    : status === "failed"
      ? "Needs attention"
      : status === "completed" || status === "success" || status === "cancelled"
        ? "Finished"
        : "Processing";
}
export function sourceAction(message = "") {
  if (/PARTS_UNAVAILABLE|Bilibili part list/i.test(message)) return false;
  return /purchas|paywall|subscription|付费|购买|restricted|source.access|required.*login|login.required|sign.in|cookie.*expir/i.test(
    message,
  );
}
