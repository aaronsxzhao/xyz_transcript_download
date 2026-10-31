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
}: {
  status: string;
  progress?: number;
  compact?: boolean;
  startedAt?: number;
  message?: string;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!startedAt || !isActiveStatus(status) || status === "pending") return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt, status]);
  const elapsed = Math.max(0, Math.floor(now / 1000 - startedAt));
  const incoming = Number.isFinite(progress)
    ? Math.max(0, Math.min(99, Math.round(progress)))
    : 0;
  const value = incoming;
  const animated = useSmoothedProgress(value, `${startedAt}:${status === 'pending' ? 'queued' : 'active'}`);
  const waiting = status === "pending" || status === "cancelling";
  const stageMessage = isActiveStatus(status) && !waiting ? message : "";
  const stageLabel = status === "summarizing" ? ["Writing full-transcript summary", "Writing sections", "Checking source accuracy", "Building coverage checklist", "Checking coverage", "Filling missing details", "Verifying additions", "Preparing the final summary"].find(label => stageMessage.startsWith(label)) : undefined;
  return (
    <div className="task-progress">
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <StatusBadge status={status} label={stageLabel} />
        {isActiveStatus(status) && !waiting && value > 0 && (
          <span
            className="ml-auto tabular-nums"
            title="Estimated overall progress"
          >
            ~{Math.round(animated)}%
          </span>
        )}
      </div>
      {isActiveStatus(status) && !waiting && (
        <div
          role="progressbar"
          aria-label={stageLabel || getStatusText(status)}
          aria-valuetext={stageMessage ? `${stageMessage}${value > 0 ? `; approximately ${value}% overall` : ""}` : undefined}
          aria-valuemin={0}
          aria-valuemax={100}
          {...(value > 0 ? { "aria-valuenow": value } : {})}
          className="task-progress-track"
        >
          <span
            className={
              value > 0 ? getStatusColor(status) : "task-indeterminate"
            }
            style={value > 0 ? { width: `${animated}%`, transition: "none" } : undefined}
          />
        </div>
      )}
      {stageMessage && <p className="task-stage-message" role="status">{stageMessage}</p>}
      {!compact && status === "summarizing" && <p className="text-xs text-gray-500">Working on this step. Progress updates as results arrive.</p>}
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
