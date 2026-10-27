import LoadError from '../components/LoadError';
import { videoFailureHint } from '../lib/videoFailure';
import { taskFailure } from '../lib/taskSource';
import { TaskProgress, sourceAction } from "../components/TaskStatus";
import { useWarmCache } from "../lib/cache";
import { extractNoteToc, normalizeNoteHeadings } from "../lib/noteMarkdown";
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
import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import { ScreenshotRecoveryContext } from '../lib/screenshotRecovery';
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
const ArticleNote = deferView(() => import('../components/ArticleNote'));
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
  const [actionError, setActionError] = useState("");
  type ReadKind = "task" | "transcript" | "version";
  const [readFailure, setReadFailure] = useState<{kind:ReadKind;message:string} | null>(null);
  const readError = readFailure?.message || "";
  const clearReadError = (kind: ReadKind) => setReadFailure(previous => previous?.kind === kind ? null : previous);
  usePageTiming(
    "video_note",
    !loading && task?.id === taskId,
    CacheKeys.VIDEO_NOTE(taskId!),
    !!readError && !loading,
  );
  const [loadAttempt, setLoadAttempt] = useState(0);
  const retryRead = () => { setReadFailure(null); setLoadAttempt(value => value + 1); };
  const [viewMode, setViewMode] = useState<ViewMode>("markdown");
  const [mapVisited, setMapVisited] = useState(false);
  const [utility, setUtility] = useState("");
  const openRecovery = useCallback(() => setUtility('recovery'), []);
  const tabPositions = useRef<Record<string, number>>({});
  const changeView = (next: ViewMode) => {
    if (next !== "transcript") clearReadError("transcript");
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
  const regenerateLock = useRef(false);

  const [notionOpen, setNotionOpen] = useState(false);
  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    clearReadError("task");
    setTaskVerified(false);
    const cached = getCache<VideoTask>(CacheKeys.VIDEO_NOTE(taskId));
    setLoading(!cached && taskRef.current?.id !== taskId);
    if (taskRef.current?.id !== taskId) {
      setActionError("");
      setReadFailure(null);
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
        }
      } catch (e) {
        console.error("Failed to load task:", e);
        if (!cancelled)
          setReadFailure({kind:"task",message:e instanceof Error ? e.message : "Cannot load video notes"});
      } finally {
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
      completedRead.current = live.id + ":active";
      setTaskVerified(false);
      return;
    }
    const key = live.id + ":" + live.status + ":" + (live.updated_at || "");
    const previous = taskRef.current;
    const wasProcessing = completedRead.current === live.id + ":active";
    if (!previous || previous.id !== live.id || completedRead.current === key) return;
    const unchanged = previous.status === live.status &&
      (!live.updated_at || Date.parse(live.updated_at) <= Date.parse(previous.updated_at || ""));
    if (!wasProcessing && (!taskVerified || unchanged)) return;
    completedRead.current = key;
    setLoadAttempt((n) => n + 1);
  }, [taskId, storeTaskSlice?.status, storeTaskSlice?.updated_at, taskVerified]);

  useEffect(() => {
    // An empty transcript during processing must not become the cached final
    // result. Invalidate older content on regeneration and fetch on completion.
    if (
      !task ||
      task.id !== taskId ||
      !["success", "failed", "cancelled"].includes(displayTask?.status || task.status)
    ) {
      setTranscript(undefined);
      setTranscriptLoading(false);
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
    clearReadError("transcript");
    setTranscriptLoading(true);
    fetchVideoTranscript(taskId, controller.signal)
      .then((data) => {
        if (active) setTranscript(data.transcript);
      })
      .catch((error) => {
        if (active)
          setReadFailure({kind:"transcript",message:error instanceof Error ? error.message : "Cannot load transcript"});
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
    displayTask?.status,
    taskVerified,
    viewMode,
    transcript,
    loadAttempt,
  ]);

  useEffect(() => {
    setVersionLoading(false);
    clearReadError("version");
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
          setReadFailure({kind:"version",message:error instanceof Error ? error.message : "Cannot load version"});
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
    setActionError("");
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
      setActionError(
        "Copy failed. Please allow clipboard access or download the Markdown file.",
      );
    } finally {
      setCopying(false);
    }
  };

  const handleDownload = async () => {
    const md = getCurrentContent();
    if (!md) return;
    setActionError("");
    try {
      const {downloadMarkdown} = await import('../lib/markdownDownload');
      downloadMarkdown(md, task?.title || "notes");
    } catch { setActionError("Could not prepare Markdown download. Please retry."); }
  };

  const handleDownloadPdf = async () => {
    const md = getCurrentContent();
    if (!md || pdfLoading) return;
    setActionError("");
    setPdfLoading(true);
    try {
      const { printVideo } = await import("../lib/videoPrint");
      await printVideo(md, task?.title || "Notes");
    } catch (e) {
      setActionError(
        e instanceof Error
          ? e.message
          : "Could not prepare the PDF. Please retry or download Markdown.",
      );
    } finally {
      setPdfLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!task || regenerateLock.current) return;
    regenerateLock.current = true;
    const owner = getAccountId(), id = task.id;
    setRegenerating(true);
    setReadFailure(null);
    setActionError("");
    try {
      await retryVideoTask(task.id);
      if (owner !== getAccountId() || taskRef.current?.id !== id) return;
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
      if (owner !== getAccountId() || taskRef.current?.id !== id) return;
      console.error("Regenerate failed:", e);
      setActionError(e instanceof Error ? e.message : "Could not regenerate notes");
    } finally {
      regenerateLock.current = false;
      setRegenerating(false);
    }
  };

  const rawContent = !task ? "" : selectedVersion ? versionContents[selectedVersion] || "" : task.markdown || "";
  const selectedStyle = selectedVersion ? task?.versions?.find(version=>version.id===selectedVersion)?.style : task?.style;
  const isOriginal = selectedStyle === 'original' && ['twitter','substack','web'].includes(task?.platform||'');
  const content = useMemo(() => isOriginal?rawContent:normalizeNoteHeadings(rawContent), [rawContent,isOriginal]);
  const getCurrentContent = () => content;

  const formatDuration = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

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
  const toc = useMemo(() => extractNoteToc(content,isOriginal), [content,isOriginal]);

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
        <LoadError message={readError || actionError || "Task not found"} onRetry={retryRead} />
        <button onClick={() => navigate(-1)} className="text-indigo-400 mt-2">
          Go Back
        </button>
      </div>
    );
  }

  const uiTask = displayTask ?? task;
  const versions = task.versions || [];
  const publicSourceFailure = ['twitter','substack','web'].includes(uiTask.platform) && sourceAction(uiTask.error || uiTask.message);

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
    <ScreenshotRecoveryContext.Provider value={!isOriginal && ['success','failed','cancelled'].includes(uiTask.status) ? openRecovery : undefined}>
    <ReaderFrame
      kind={isOriginal ? task.platform==='web'?'Original article':'Original post' : task.source_metadata?.type==='audio'?'Audio':'Video'}
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
          {!isOriginal && task.duration > 0 && <span>{formatDuration(task.duration)}</span>}
          {selectedStyle && <span>{selectedStyle}</span>}
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
                {content && (
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
            {!isOriginal && ["success", "failed", "cancelled"].includes(uiTask.status) && (
              <>
                {task.source_metadata?.type !== 'audio' && <button onClick={() => setUtility("recovery")}>
                  <RotateCcw size={16} />
                  Downloads & screenshot recovery
                </button>}
                <RegenerateAction
                  onConfirm={() => void handleRegenerate()}
                  busy={regenerating}
                  description="Process this recording again with your current settings. Saved versions remain available."
                />
              </>
            )}
            {isOriginal && <button onClick={()=>void handleRegenerate()} disabled={regenerating}><RotateCcw size={16}/>Refresh original</button>}
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
          ).filter(([mode])=>!isOriginal||mode!=='transcript').map(([mode, label]) => (
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
              {isOriginal && mode==='markdown' ? 'Original text' : label}
            </button>
          ))}
        </>
      }
    >
      {readError && <LoadError message={readError} onRetry={retryRead} />}
      {actionError && <div role="alert" className="text-sm text-red-300 mb-3">
        {actionError}{" "}<button className="underline" onClick={() => setActionError("")}>Dismiss</button>
      </div>}
      {!["success", "failed", "cancelled"].includes(uiTask.status) && content &&
        <p role="status" className="text-sm text-gray-400 mb-3">A new version is processing. Showing the saved note.</p>}
      {uiTask.status === "cancelled" && (
        <p role="status" className="text-sm text-gray-400 mb-3">
          Processing was cancelled. {content ? "Showing the saved note." : "No saved note is available yet. You can retry from the actions menu."}
        </p>
      )}
      {utility && (
        <ReaderDetails
          kind={utility}
          task={uiTask}
          selectedVersion={selectedVersion}
          onVersion={(id) => {
            clearReadError("version");
            setActionError("");
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
              {content && <p className="text-xs text-gray-300 mb-2">The saved note below is still available.</p>}
              {(task.error || task.message) && (
                <p className="text-xs text-red-400/80 mb-2">
                  {publicSourceFailure ? taskFailure(uiTask.error || uiTask.message, uiTask.platform).message : task.error && /^[A-Z_]+$/.test(task.error)
                    ? task.message && task.message !== "Failed" && task.message !== task.error ? task.message : videoFailureHint(task)
                    : task.error || task.message}
                </p>
              )}
              {/^https?:\/\//.test(task.url) && (
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
                {!publicSourceFailure && <Link
                  to="/settings"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-hover hover:bg-dark-border text-gray-300 text-xs rounded-lg transition-colors"
                >
                  Check Settings
                </Link>}
              </div>
            </div>
          </div>
        </div>
      )}

      {uiTask.status === 'discovered' && !content ? (
        <section className="reader-processing space-y-3" aria-label="Unprocessed content">
          <h2 className="text-lg font-semibold">Not processed yet</h2>
          <p className="text-sm text-gray-400">This source has been added. Start processing to create its saved note.</p>
          <button className="ui-button ui-button-primary" disabled={regenerating} onClick={handleRegenerate}>{regenerating?'Submitting…':'Start processing'}</button>
        </section>
      ) : !["success", "failed", "cancelled"].includes(uiTask.status) &&
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
                isOriginal ? <ArticleNote markdown={content} readerTitle={title} readerMeta={{author:task.channel,published:task.published_at}} attachments={selectedVersion ? [] : task.source_metadata?.attachments} fallback={<PlainNote markdown={content} preserveSource readerTitle={title} readerMeta={{author:task.channel,published:task.published_at}}/>}/> : <MarkdownPreview
                  markdown={content}
                  readerTitle={title}
                  fallback={<PlainNote markdown={content} readerTitle={title}/>}
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
              {transcriptLoading || (!taskVerified && transcript === undefined) ? (
                <p role="status" className="reader-loading">
                  {!readError && <Loader2 size={18} className="animate-spin" />}
                  {readError ? "Retry above to load the transcript." : !taskVerified ? "Waiting for the latest transcript…" : "Loading transcript…"}
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
          selectedVersion={selectedVersion}
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
    </ScreenshotRecoveryContext.Provider>
  );
}
