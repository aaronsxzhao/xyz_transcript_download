import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchFavoriteFolders,
  fetchFavoritePage,
  type FavoriteFolder,
  type FavoritePage,
} from "../../lib/bilibiliFavorites";
import {
  generateVideoNote,
  getVideoProcessingDefaults,
  type VideoNoteRequest,
} from "../../lib/api";
import { getAuthGeneration } from "../../lib/auth";
import CachedImage from "../CachedImage";

export default function BilibiliFavorites({
  onImported,
}: {
  onImported: () => void;
}) {
  const [folders, setFolders] = useState<FavoriteFolder[]>([]);
  const [folder, setFolder] = useState(0);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<FavoritePage | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [attempt, setAttempt] = useState(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const reset = () => {
      setFolders([]);
      setFolder(0);
      setPage(1);
      setData(null);
      setSelected(new Set());
      setBusy(false);
      setMessage("");
      setError("");
      setAttempt((value) => value + 1);
    };
    window.addEventListener("xyz:session-changed", reset);
    return () => {
      mounted.current = false;
      window.removeEventListener("xyz:session-changed", reset);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    const generation = getAuthGeneration();
    setLoading(true);
    setError("");
    setData(null);
    setSelected(new Set());
    const current = () =>
      !controller.signal.aborted && generation === getAuthGeneration();
    void (async () => {
      if (!folder) {
        const result = await fetchFavoriteFolders(controller.signal);
        if (!current()) return;
        setFolders(result.folders);
        if (result.folders.length) setFolder(result.folders[0].id);
      } else {
        const result = await fetchFavoritePage(folder, page, controller.signal);
        if (current()) setData(result);
      }
    })()
      .catch((err) => {
        if (current())
          setError(
            err instanceof Error ? err.message : "Could not read favorites.",
          );
      })
      .finally(() => {
        clearTimeout(timer);
        if (current()) setLoading(false);
      });
    const timedOut = () => {
      if (generation === getAuthGeneration()) {
        setLoading(false);
        setError("Bilibili favorites took too long to load. Please retry.");
      }
    };
    controller.signal.addEventListener("abort", timedOut, { once: true });
    return () => {
      controller.signal.removeEventListener("abort", timedOut);
      clearTimeout(timer);
      controller.abort();
    };
  }, [folder, page, attempt]);

  async function processSelected() {
    const videos =
      data?.videos.filter(
        (video) =>
          selected.has(video.bvid) && video.available && !video.imported,
      ) || [];
    if (busy || !videos.length) return;
    const generation = getAuthGeneration();
    const current = () => mounted.current && generation === getAuthGeneration();
    setBusy(true);
    setError("");
    let queued = 0,
      skipped = 0;
    try {
      const defaults = getVideoProcessingDefaults();
      for (const [index, video] of videos.entries()) {
        if (!current()) break;
        setMessage(`Submitting ${index + 1}/${videos.length}…`);
        const result = await generateVideoNote({
          ...defaults,
          url: video.url,
          title: video.title,
          platform: "bilibili",
          skip_existing: true,
          style:
            typeof defaults.style === "string" ? defaults.style : "detailed",
          formats: Array.isArray(defaults.formats)
            ? (defaults.formats as string[])
            : ["toc", "summary", "screenshot"],
        } as VideoNoteRequest);
        if (!current()) break;
        if (result.skipped) skipped++;
        else queued++;
        setData((previous) =>
          previous
            ? {
                ...previous,
                videos: previous.videos.map((row) =>
                  row.bvid === video.bvid ? { ...row, imported: true } : row,
                ),
              }
            : previous,
        );
        setSelected((previous) => {
          const next = new Set(previous);
          next.delete(video.bvid);
          return next;
        });
      }
    } catch (err) {
      if (current())
        setError(
          `${err instanceof Error ? err.message : "Submission failed."} Remaining videos were not submitted. Refresh before retrying.`,
        );
    } finally {
      if (current()) {
        setBusy(false);
        setMessage(
          `${queued} queued${skipped ? `, ${skipped} already imported` : ""}. Follow progress in Processing.`,
        );
        if (queued || skipped) onImported();
      }
    }
  }
  const available =
    data?.videos.filter((video) => video.available && !video.imported) || [];
  return (
    <section
      className="space-y-3 rounded-xl border border-dark-border bg-dark-surface p-4"
      aria-label="Bilibili favorites"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Bilibili favorites</h2>
          <p className="text-sm text-gray-400">
            Choose videos to process using your saved video settings. Existing
            imports are skipped.
          </p>
        </div>
        <Link to="/settings" className="text-sm text-indigo-300">
          Bilibili account settings
        </Link>
      </div>
      {busy && (
        <p className="text-xs text-gray-400">
          Closing this panel stops remaining submissions. Queued tasks continue
          processing.
        </p>
      )}
      {error && (
        <div role="alert" className="text-sm text-amber-300">
          {error}{" "}
          <button
            disabled={busy}
            onClick={() => setAttempt((value) => value + 1)}
            className="underline"
          >
            Retry loading
          </button>
        </div>
      )}
      {folders.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <select
            aria-label="Favorite folder"
            disabled={busy || loading}
            value={folder}
            onChange={(e) => {
              setFolder(Number(e.target.value));
              setPage(1);
              setMessage("");
            }}
            className="rounded bg-dark-hover p-2 text-sm"
          >
            {folders.map((row) => (
              <option key={row.id} value={row.id}>
                {row.title} ({row.count})
              </option>
            ))}
          </select>
          <button
            disabled={busy || loading || !selected.size}
            onClick={() => void processSelected()}
            className="rounded-lg bg-indigo-600 px-3 py-2 text-sm disabled:opacity-50"
          >
            {busy ? "Submitting…" : `Process selected (${selected.size})`}
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="text-sm text-gray-400">
          {message}
        </p>
      )}
      {loading ? (
        <p role="status" className="text-sm text-gray-400">
          Loading favorites…
        </p>
      ) : !error && !folders.length ? (
        <p className="text-sm text-gray-400">
          This Bilibili account has no created favorite folders.
        </p>
      ) : (
        data && (
          <>
            {available.length > 0 && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={available.every((video) => selected.has(video.bvid))}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? new Set(available.map((video) => video.bvid))
                        : new Set(),
                    )
                  }
                />
                Select available videos on this page
              </label>
            )}
            {!data.videos.length && (
              <p className="text-sm text-gray-400">This folder is empty.</p>
            )}
            <div className="divide-y divide-dark-border">
              {data.videos.map((video, index) => (
                <label
                  key={video.bvid || index}
                  className="flex items-center gap-3 py-3"
                >
                  <input
                    type="checkbox"
                    aria-label={`Select ${video.title}`}
                    disabled={busy || !video.available || video.imported}
                    checked={selected.has(video.bvid)}
                    onChange={(e) =>
                      setSelected((previous) => {
                        const next = new Set(previous);
                        if (e.target.checked) next.add(video.bvid);
                        else next.delete(video.bvid);
                        return next;
                      })
                    }
                  />
                  <CachedImage
                    src={video.thumbnail}
                    className="h-14 w-24 shrink-0 rounded"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block line-clamp-2 text-sm font-medium">
                      {video.title}
                    </span>
                    <span className="block text-xs text-gray-400">
                      {video.uploader} · {Math.ceil(video.duration / 60)} min ·{" "}
                      {!video.available
                        ? "Unavailable"
                        : video.imported
                          ? "Already imported"
                          : "Ready to process"}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <div className="flex items-center gap-3 text-sm">
              <button
                disabled={busy || page === 1}
                onClick={() => setPage((value) => value - 1)}
              >
                Previous
              </button>
              <span>Page {page}</span>
              <button
                disabled={busy || !data.has_more}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          </>
        )
      )}
    </section>
  );
}
