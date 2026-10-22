import { TaskProgress } from "../components/TaskStatus";
import { useWarmCache } from "../lib/cache";
import { extractNoteToc } from "../lib/noteMarkdown";
import ReaderFrame, {
  ReaderMenu,
  MoreReaderActions,
  RegenerateAction,
} from "../components/ReaderChrome";
import { useRecordReading } from "../lib/readingHistory";
import { useReadingPosition } from "../lib/reading";
import { markdownToSafeHtml } from "../lib/safeHtml";
import { getAccountId } from "../lib/preferences";
import { CacheKeys, getCache, setCache, removeCache } from "../lib/cache";
import { usePageTiming } from "../lib/pageTiming";
import { useEffect, useState, useMemo, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  Copy,
  Download,
  Check,
  FileText,
  Map,
  Loader2,
  FileDown,
  XCircle,
  ExternalLink,
  RotateCcw,
} from "lucide-react";
import {
  fetchVideoTask,
  fetchVideoTranscript,
  fetchVideoVersion,
  retryVideoTask,
  type VideoTask,
} from "../lib/api";
import { useStore, mergeVideoTaskPair } from "../lib/store";
import { deferView } from "../components/DeferredView";
import PlainNote from "../components/PlainNote";
const MarkdownPreview = deferView(
  () => import("../components/video/MarkdownPreview"),
);
const ReaderDetails = deferView(
  () => import("../components/video/ReaderDetails"),
);
const TranscriptPanel = deferView(
  () => import("../components/video/TranscriptPanel"),
);
const NotionExport = deferView(
  () => import("../components/PodcastNotionExport"),
);
const MindMapView = deferView(() => import("../components/video/MindMapView"));
const preloadMindMap = () =>
  import("../components/video/MindMapView").then((module) =>
    module.preloadMindMap(),
  );

type ViewMode = "markdown" | "mindmap" | "transcript";

export default function VideoViewer() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<VideoTask | null>(() =>
    getCache(CacheKeys.VIDEO_NOTE(taskId!)),
  );
  const taskRef = useRef(task);
  taskRef.current = task;
  const storeTaskSlice = useStore((s) =>
    taskId ? s.videoTasks.find((t) => t.id === taskId) : undefined,
  );
  const displayTask = useMemo(() => {
    if (!task) return null;
    return storeTaskSlice ? mergeVideoTaskPair(storeTaskSlice, task) : task;
  }, [task, storeTaskSlice]);
  const [loading, setLoading] = useState(
    () => !getCache(CacheKeys.VIDEO_NOTE(taskId!)),
  );
  const [taskVerified, setTaskVerified] = useState(false);
  const [error, setError] = useState("");
  usePageTiming(
    "video_note",
    !loading && task?.id === taskId,
    CacheKeys.VIDEO_NOTE(taskId!),
    !!error && !loading,
  );
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("markdown");
  const [mapVisited, setMapVisited] = useState(false);
  const [utility, setUtility] = useState("");
  const tabPositions = useRef<Record<string, number>>({});
  const changeView = (next: ViewMode) => {
    const main = document.querySelector("main");
    tabPositions.current[viewMode] = main?.scrollTop || 0;
    if (next === "mindmap") setMapVisited(true);
    setViewMode(next);
    requestAnimationFrame(() => {
      if (main) main.scrollTop = tabPositions.current[next] || 0;
    });
  };
  const [selectedVersion, setSelectedVersion] = useState<string>("");
  useWarmCache<VideoTask>(CacheKeys.VIDEO_NOTE(taskId!), (value) => {
    setTask(value);
    setLoading(false);
  });
  const [versionContents, setVersionContents] = useState<
    Record<string, string>
  >({});
  const [versionLoading, setVersionLoading] = useState(false);
  const [transcript, setTranscript] = useState<
    VideoTask["transcript"] | undefined
  >();
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copying, setCopying] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const [notionOpen, setNotionOpen] = useState(false);
  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    let inFlight = false;
    setTaskVerified(false);
    const cached = getCache<VideoTask>(CacheKeys.VIDEO_NOTE(taskId));
    setLoading(!cached && taskRef.current?.id !== taskId);
    if (taskRef.current?.id !== taskId) {
      setTask(cached);
      setSelectedVersion("");
      setVersionContents({});
      setTranscript(undefined);
      setMapVisited(false);
      setViewMode("markdown");
      setUtility("");
      tabPositions.current = {};
    }

    const load = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      const owner = getAccountId();
      try {
        const data = await fetchVideoTask(taskId);
        if (!cancelled && owner === getAccountId()) {
          setTask(data);
          if (!["success", "failed", "cancelled"].includes(data.status))
            useStore.getState().updateVideoTask(data);
          setTaskVerified(true);
          if (data.status === "success")
            setCache(CacheKeys.VIDEO_NOTE(taskId), data, owner);
          else removeCache(CacheKeys.VIDEO_NOTE(taskId));
          setError("");
        }
      } catch (e) {
        console.error("Failed to load task:", e);
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Cannot load video notes");
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [taskId, loadAttempt]);

  const completedRead = useRef("");
  useEffect(() => {
    const live = storeTaskSlice;
    if (!live || live.id !== taskId) return;
    if (!["success", "failed", "cancelled"].includes(live.status)) {
      completedRead.current = "";
      return;
    }
    const key = live.id + ":" + live.status + ":" + (live.updated_at || "");
    if (
      completedRead.current === key ||
      taskRef.current?.status === live.status
    )
      return;
    completedRead.current = key;
    setLoadAttempt((n) => n + 1);
  }, [taskId, storeTaskSlice?.status, storeTaskSlice?.updated_at]);

  useEffect(() => {
    // An empty transcript during processing must not become the cached final
    // result. Invalidate older content on regeneration and fetch on completion.
    if (
      !task ||
      task.id !== taskId ||
      !["success", "failed", "cancelled"].includes(task.status)
    ) {
      setTranscript(undefined);
      return;
    }
    // Cached notes may predate a regeneration started in another tab. Confirm
    // the current task status before caching its separately loaded transcript.
    if (
      !taskVerified ||
      !taskId ||
      viewMode !== "transcript" ||
      transcript !== undefined
    )
      return;
    let active = true;
    const controller = new AbortController();
    setTranscriptLoading(true);
    fetchVideoTranscript(taskId, controller.signal)
      .then((data) => {
        if (active) setTranscript(data.transcript);
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error ? error.message : "Cannot load transcript",
          );
      })
      .finally(() => {
        if (active) setTranscriptLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [
    taskId,
    task?.id,
    task?.status,
    taskVerified,
    viewMode,
    transcript,
    loadAttempt,
  ]);

  useEffect(() => {
    setVersionLoading(false);
    if (!taskId || !selectedVersion || selectedVersion in versionContents)
      return;
    let active = true;
    const controller = new AbortController();
    setVersionLoading(true);
    fetchVideoVersion(taskId, selectedVersion, controller.signal)
      .then((version) => {
        if (active)
          setVersionContents((cache) => ({
            ...cache,
            [version.id]: version.content,
          }));
      })
      .catch((error) => {
        if (active)
          setError(
            error instanceof Error ? error.message : "Cannot load version",
          );
      })
      .finally(() => {
        if (active) setVersionLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [taskId, selectedVersion, versionContents, loadAttempt]);

  const handleCopy = async () => {
    const md = getCurrentContent();
    if (!md || copying) return;
    setCopying(true);
    try {
      try {
        // Passing promised HTML keeps clipboard permission tied to the click
        // on Safari, even while the formatter module is still downloading.
        const html = markdownToSafeHtml(md).then(
          (value) => new Blob([value], { type: "text/html" }),
        );
        void html.catch(() => {});
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/html": html,
            "text/plain": new Blob([md], { type: "text/plain" }),
          }),
        ]);
      } catch {
        await navigator.clipboard.writeText(md);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(
        "Copy failed. Please allow clipboard access or download the Markdown file.",
      );
    } finally {
      setCopying(false);
    }
  };

  const handleDownload = () => {
    const md = getCurrentContent();
    if (!md || !task) return;
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${task.title || "notes"}.md`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  };

  const handleDownloadPdf = async () => {
    const md = getCurrentContent();
    if (!md || pdfLoading) return;
    setPdfLoading(true);
    try {
      const { printVideo } = await import("../lib/videoPrint");
      await printVideo(md, task?.title || "Notes");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not prepare the PDF. Please retry or download Markdown.",
      );
    } finally {
      setPdfLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!task || regenerating) return;
    setRegenerating(true);
    setError("");
    try {
      await retryVideoTask(task.id);
      completedRead.current = "";
      const pending = {
        ...task,
        status: "pending",
        progress: 0,
        message: "Queued for processing...",
        error: "",
      };
      taskRef.current = pending;
      setTask(pending);
      useStore.getState().updateVideoTask(pending);
      setSelectedVersion("");
    } catch (e) {
      console.error("Regenerate failed:", e);
      setError(e instanceof Error ? e.message : "Could not regenerate notes");
    } finally {
      setRegenerating(false);
    }
  };

  const getCurrentContent = (): string => {
    if (!task) return "";
    if (selectedVersion) return versionContents[selectedVersion] || "";
    return task.markdown || "";
  };

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const content = getCurrentContent();
  useReadingPosition(
    `video:${taskId}`,
    undefined,
    !loading && task?.id === taskId && !!content && viewMode === "markdown",
  );
  useRecordReading(
    {
      id: taskId!,
      kind: "video",
      title: task?.title || "",
      source: task?.channel,
      thumbnail: task?.thumbnail,
    },
    !loading &&
      taskVerified &&
      task?.status === "success" &&
      !!content &&
      viewMode === "markdown",
  );
  const toc = useMemo(() => extractNoteToc(content), [content]);

  const scrollToHeading = (slug: string) => {
    const el = document.getElementById(slug);
    if (!el) return;
    el.scrollIntoView({ block: "start" });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-gray-500">
        <p role="alert">{error || "Task not found"}</p>
        <button
          onClick={() => setLoadAttempt((value) => value + 1)}
          className="text-indigo-400 mt-2"
        >
          Retry
        </button>
        <button onClick={() => navigate(-1)} className="text-indigo-400 mt-2">
          Go Back
        </button>
      </div>
    );
  }

  const uiTask = displayTask ?? task;
  const versions = task.versions || [];

  const title =
    task.title ||
    (task.platform === "local"
      ? task.url
          .split(/[\\/]/)
          .pop()
          ?.replace(/\.[^.]+$/, "")
      : task.url) ||
    "Untitled video";
  return (
    <ReaderFrame
      kind="Video"
      title={title}
      sections={
        viewMode === "markdown"
          ? toc.map((item) => ({
              id: item.slug,
              title: item.text,
              level: item.level,
            }))
          : []
      }
      onNavigate={scrollToHeading}
      metadata={
        <>
          <span>{task.channel || task.platform || "Video"}</span>
          {task.published_at && (
            <span>
              Published {new Date(task.published_at).toLocaleDateString()}
            </span>
          )}
          {task.duration > 0 && <span>{formatDuration(task.duration)}</span>}
          {task.style && <span>{task.style}</span>}
          {selectedVersion && (
            <span>
              Saved version ·{" "}
              {versions.findIndex(
                (version) => version.id === selectedVersion,
              ) >= 0
                ? `v${versions.length - versions.findIndex((version) => version.id === selectedVersion)}`
                : selectedVersion}
            </span>
          )}
        </>
      }
      actions={
        <>
          {content && (
            <>
              <button
                onClick={handleCopy}
                disabled={copying}
                className="reader-action"
                aria-label={
                  copying ? "Copying note" : copied ? "Copied" : "Copy note"
                }
              >
                {copying ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : copied ? (
                  <Check size={15} />
                ) : (
                  <Copy size={15} />
                )}{" "}
                {copied ? "Copied" : "Copy"}
              </button>
              <ReaderMenu
                label="Export"
                busy={pdfLoading}
                outlined
                icon={
                  pdfLoading ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Download size={15} />
                  )
                }
              >
                <button onClick={handleDownload} title="Download .md">
                  <Download size={16} />
                  Markdown
                </button>
                {uiTask.status === "success" && (
                  <>
                    <button
                      onClick={handleDownloadPdf}
                      disabled={pdfLoading}
                      aria-busy={pdfLoading}
                      title="Download PDF"
                    >
                      {pdfLoading ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <FileDown size={16} />
                      )}{" "}
                      {pdfLoading ? "Preparing PDF…" : "PDF"}
                    </button>
                    <button
                      onClick={() => setNotionOpen(true)}
                      title="Send to Notion"
                    >
                      <ExternalLink size={16} />
                      Send to Notion
                    </button>
                  </>
                )}
              </ReaderMenu>
            </>
          )}
          <MoreReaderActions>
            <button onClick={() => setUtility("source")}>
              <FileText size={16} />
              Source details
            </button>
            {versions.length > 0 && (
              <button onClick={() => setUtility("versions")}>
                <FileText size={16} />
                Version history
              </button>
            )}
            {["success", "failed", "cancelled"].includes(uiTask.status) && (
              <>
                <button onClick={() => setUtility("recovery")}>
                  <RotateCcw size={16} />
                  Downloads & screenshot recovery
                </button>
                <RegenerateAction
                  onConfirm={() => void handleRegenerate()}
                  busy={regenerating}
                  description="Process this video again with your current settings. Saved versions remain available."
                />
              </>
            )}
          </MoreReaderActions>
        </>
      }
      tabs={
        <>
          {(
            [
              ["markdown", "Summary"],
              ["transcript", "Transcript"],
              ["mindmap", "Mind map"],
            ] as const
          ).map(([mode, label]) => (
            <button
              key={mode}
              role="tab"
              aria-selected={viewMode === mode}
              tabIndex={viewMode === mode ? 0 : -1}
              aria-controls={`video-${mode}`}
              onPointerEnter={() => {
                if (mode === "mindmap") void preloadMindMap().catch(() => {});
              }}
              onFocus={() => {
                if (mode === "mindmap") void preloadMindMap().catch(() => {});
              }}
              onClick={() => changeView(mode)}
            >
              {mode === "mindmap" ? <Map size={15} /> : <FileText size={15} />}{" "}
              {label}
            </button>
          ))}
        </>
      }
    >
      {error && (
        <div role="alert" className="text-sm text-red-300 mb-3">
          {error}{" "}
          <button
            className="underline"
            onClick={() => setLoadAttempt((value) => value + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {utility && (
        <ReaderDetails
          kind={utility}
          task={uiTask}
          selectedVersion={selectedVersion}
          onVersion={(id) => {
            setError("");
            setSelectedVersion(id);
          }}
          onClose={() => setUtility("")}
          onRestored={() => setLoadAttempt((value) => value + 1)}
          fallback={<p role="status">Loading details…</p>}
        />
      )}
      {uiTask.status === "success" && task.error && !utility && (
        <p role="status" className="text-sm text-amber-300 mb-4">
          The summary is saved. {task.error}{" "}
          <button className="underline" onClick={() => setUtility("recovery")}>
            Review screenshots
          </button>
        </p>
      )}
      {/* Failed state banner */}
      {uiTask.status === "failed" && (
        <div className="flex-shrink-0 mb-3 p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-red-400 mb-1">
                Processing Failed
              </h3>
              {(task.error || task.message) && (
                <p className="text-xs text-red-400/80 mb-2">
                  {task.error || task.message}
                </p>
              )}
              {task.url && (
                <a
                  href={task.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 mb-2"
                >
                  <ExternalLink size={10} />
                  <span className="truncate max-w-xs">{task.url}</span>
                </a>
              )}
              <div className="flex items-center gap-2 mt-1">
                <button
                  onClick={handleRegenerate}
                  disabled={regenerating}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
                >
                  <RotateCcw
                    size={12}
                    className={regenerating ? "animate-spin" : ""}
                  />
                  Retry
                </button>
                <Link
                  to="/settings"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-hover hover:bg-dark-border text-gray-300 text-xs rounded-lg transition-colors"
                >
                  Check Settings
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {!["success", "failed", "cancelled"].includes(uiTask.status) &&
      !content ? (
        <div className="reader-processing">
          <TaskProgress
            status={uiTask.status}
            progress={uiTask.progress}
            startedAt={uiTask.started_at}
          />
          <p>{uiTask.message || "Waiting for processing…"}</p>
        </div>
      ) : (
        <>
          <div
            hidden={viewMode !== "markdown"}
            role="tabpanel"
            id="video-markdown"
          >
            <div
              id="video-content-scroll"
              aria-label="Video note content"
              className="reader-body"
            >
              {versionLoading ? (
                <p role="status" className="reader-loading">
                  <Loader2 className="animate-spin" size={18} />
                  Loading saved version…
                </p>
              ) : (
                <MarkdownPreview
                  task={{ ...uiTask, markdown: content }}
                  fallback={<PlainNote markdown={content} />}
                />
              )}
            </div>
          </div>
          {mapVisited && (
            <div
              hidden={viewMode !== "mindmap"}
              role="tabpanel"
              id="video-mindmap"
            >
              {versionLoading ? (
                <p role="status">Loading saved version…</p>
              ) : (
                <MindMapView
                  markdown={content}
                  active={viewMode === "mindmap"}
                  fallback={<p role="status">Loading mind map tools…</p>}
                />
              )}
            </div>
          )}
          {viewMode === "transcript" && (
            <div role="tabpanel" id="video-transcript" className="reader-body">
              {transcriptLoading ? (
                <p role="status" className="reader-loading">
                  <Loader2 size={18} className="animate-spin" />
                  Loading transcript…
                </p>
              ) : (
                <TranscriptPanel
                  transcript={transcript || null}
                  fallback={
                    <p className="whitespace-pre-wrap">
                      {transcript?.text || "No transcript available."}
                    </p>
                  }
                />
              )}
            </div>
          )}
        </>
      )}

      {notionOpen && (
        <NotionExport
          key={task.id}
          task={task}
          content={content}
          onClose={() => setNotionOpen(false)}
          fallback={
            <p role="status">
              Loading export…{" "}
              <button onClick={() => setNotionOpen(false)}>Cancel</button>
            </p>
          }
        />
      )}
    </ReaderFrame>
  );
}
