import { useState, useEffect } from "react";
import {
  getStatusColor,
  getStatusIcon,
  getStatusText,
  isActiveStatus,
} from "../lib/statusUtils";
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className="task-status-badge">
      {getStatusIcon(status)}
      {getStatusText(status)}
    </span>
  );
}
export function TaskProgress({
  status,
  progress = 0,
  compact = false,
  startedAt = 0,
}: {
  status: string;
  progress?: number;
  compact?: boolean;
  startedAt?: number;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!startedAt || !isActiveStatus(status) || status === "pending") return;
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, [startedAt, status]);
  const elapsed = Math.max(0, Math.floor(now / 1000 - startedAt));
  const value = Number.isFinite(progress)
    ? Math.max(0, Math.min(99, Math.round(progress)))
    : 0;
  const waiting = status === "pending" || status === "cancelling";
  return (
    <div className="task-progress">
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <StatusBadge status={status} />
        {isActiveStatus(status) && !waiting && value > 0 && (
          <span
            className="ml-auto tabular-nums"
            title="Estimated overall progress"
          >
            ~{value}%
          </span>
        )}
      </div>
      {isActiveStatus(status) && !waiting && (
        <div
          role="progressbar"
          aria-label={getStatusText(status)}
          aria-valuemin={0}
          aria-valuemax={100}
          {...(value > 0 ? { "aria-valuenow": value } : {})}
          className="task-progress-track"
        >
          <span
            className={
              value > 0 ? getStatusColor(status) : "task-indeterminate"
            }
            style={value > 0 ? { width: `${value}%` } : undefined}
          />
        </div>
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
  return /purchas|paywall|付费|购买|restricted|source.access|required.*login|login.required|sign.in|cookie.*expir/i.test(
    message,
  );
}
