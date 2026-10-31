import { Upload, X } from "lucide-react";
import type { VideoUploadSession } from "../lib/store";
const formatBytes = (n: number) => `${(Math.max(0, n) / 1048576).toFixed(1)} MB`;
export default function UploadSessionItem({
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
