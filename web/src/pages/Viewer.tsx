import SourceAccessNotice, {
  sourceBlocked,
} from "../components/SourceAccessNotice";
import { useWarmCache } from "../lib/cache";
import SummaryText from "../components/SummaryText";
import ReaderFrame, {
  ReaderMenu,
  MoreReaderActions,
  RegenerateAction,
} from "../components/ReaderChrome";
import { useRecordReading } from "../lib/readingHistory";
import { useReadingPosition } from "../lib/reading";
import LoadError from "../components/LoadError";
import { deferView } from "../components/DeferredView";
const TranscriptSegments = deferView(
  () => import("../components/TranscriptSegments"),
);
const PodcastNotionExport = deferView(
  () => import("../components/PodcastNotionExport"),
);
import { markdownToSafeHtml } from "../lib/safeHtml";
import {
  summaryChapters,
  summaryIntroduction,
  summaryToMarkdown,
} from "../lib/summaryReading";
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  FileText,
  MessageSquare,
  CheckCircle,
  Quote,
  ChevronDown,
  ChevronUp,
  Loader2,
  ExternalLink,
  Copy,
  Check,
  Download,
  FileDown,
} from "lucide-react";
import {
  ApiError,
  fetchJob,
  fetchSummary,
  fetchTranscript,
  resummarizeEpisode,
  type Summary,
  type Transcript,
} from "../lib/api";
import { getAccessToken } from "../lib/auth";
import { useStore } from "../lib/store";
import { getCache, setCache, CacheKeys } from "../lib/cache";
import { getAccountId } from "../lib/preferences";
import { usePageTiming } from "../lib/pageTiming";

type Tab = "summary" | "transcript";

export default function Viewer() {
  const { eid } = useParams<{ eid: string }>();
  const currentEid = useRef(eid);
  currentEid.current = eid;
  const loadVersion = useRef(0);
  const [activeTab, setActiveTab] = useState<Tab>("summary");
  const [summary, setSummary] = useState<Summary | null>(() =>
    getCache(CacheKeys.SUMMARY(eid!)),
  );
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [loading, setLoading] = useState(
    () => !getCache(CacheKeys.SUMMARY(eid!)),
  );
  useWarmCache<Summary>(CacheKeys.SUMMARY(eid!), (value) => {
    setSummary(value);
    setExpandedTopics(new Set(summaryChapters(value).map(([topic]) => topic)));
    setLoading(false);
  });
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [resummarizing, setResummarizing] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  usePageTiming(
    "viewer",
    !loading && (summary?.episode_id === eid || transcript?.episode_id === eid),
    CacheKeys.SUMMARY(eid!),
    !!error && !loading,
  );
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(
    () =>
      new Set(
        summaryChapters(getCache<Summary>(CacheKeys.SUMMARY(eid!))).map(
          ([topic]) => topic,
        ),
      ),
  );
  const [copied, setCopied] = useState(false);
  const [copying, setCopying] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);

  useReadingPosition(
    `podcast:${eid}`,
    undefined,
    !loading && summary?.episode_id === eid && activeTab === "summary",
  );
  useRecordReading(
    { id: eid!, kind: "podcast", title: summary?.title || "" },
    !loading &&
      !!summary &&
      summary.episode_id === eid &&
      !summary.quality_warning &&
      activeTab === "summary",
  );
  const [notionOpen, setNotionOpen] = useState(false);
  const loadTranscript = useCallback(async () => {
    const requestedEid = eid;
    setTranscriptLoading(true);
    try {
      const data = await fetchTranscript(eid!);
      if (requestedEid === currentEid.current) setTranscript(data);
      return data;
    } catch {
      if (requestedEid === currentEid.current)
        setError("Cannot load the transcript. Please retry.");
      return null;
    } finally {
      if (requestedEid === currentEid.current) setTranscriptLoading(false);
    }
  }, [eid]);

  useEffect(() => {
    if (!eid) return;
    const cached = getCache<Summary>(CacheKeys.SUMMARY(eid));
    setSummary(cached);
    setExpandedTopics(new Set(summaryChapters(cached).map(([topic]) => topic)));
    setTranscript(null);
    setActiveTab("summary");
    setResummarizing(false);
    setActionError("");
    void loadData();
    return () => {
      loadVersion.current += 1;
    };
  }, [eid]);

  useEffect(() => {
    if (activeTab === "transcript" && !transcript) void loadTranscript();
  }, [activeTab, transcript, loadTranscript]);

  async function loadData() {
    const cached = getCache<Summary>(CacheKeys.SUMMARY(eid!));
    setLoading(!cached);
    setError("");
    const requestedEid = eid;
    const owner = getAccountId();
    const version = ++loadVersion.current;
    const current = () =>
      version === loadVersion.current &&
      requestedEid === currentEid.current &&
      owner === getAccountId();
    try {
      const data = await fetchSummary(eid!);
      if (!current()) return;
      setSummary(data);
      setCache(CacheKeys.SUMMARY(eid!), data, owner);
      setExpandedTopics(new Set(summaryChapters(data).map(([topic]) => topic)));
    } catch (err) {
      if (!current()) return;
      if (cached) setError("Cannot refresh this summary. Please retry.");
      else if (err instanceof ApiError && err.status === 404) {
        // Episodes with a transcript but no summary still open normally.
        const fallback = await loadTranscript();
        if (requestedEid !== currentEid.current) return;
        if (fallback) setActiveTab("transcript");
        else setError("Cannot load this episode. Please retry.");
      } else if (err instanceof TypeError)
        setError(
          "The summary connection was interrupted. Check your connection and retry. Your saved summary has not been deleted.",
        );
      else if (err instanceof ApiError && err.status === 401)
        setError("Your session has expired. Please sign in again.");
      else
        setError(
          err instanceof Error
            ? err.message
            : "Cannot load this summary. Please retry.",
        );
    } finally {
      if (current()) {
        setLoading(false);
      }
    }
  }


  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { updateJob } = useStore();

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [eid]);

  async function handleResummarize() {
    if (!eid || resummarizing) return;

    try {
      setResummarizing(true);
      setError("");
      const result = await resummarizeEpisode(eid);

      updateJob({
        job_id: result.job_id,
        status: "pending",
        progress: 0,
        message: "Re-summarizing...",
        episode_id: eid,
        episode_title: summary?.title || "",
      });

      let polling = false;
      pollRef.current = setInterval(async () => {
        if (polling || eid !== currentEid.current) return;
        polling = true;
        try {
          const job = await fetchJob(result.job_id);
          if (eid !== currentEid.current) return;
          updateJob(job);
          if (job.status === "completed") {
            const fresh = await fetchSummary(eid);
            if (eid !== currentEid.current) return;
            setSummary(fresh);
            setCache(CacheKeys.SUMMARY(eid), fresh);
            setExpandedTopics(
              new Set(summaryChapters(fresh).map(([topic]) => topic)),
            );
            setResummarizing(false);
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } else if (["failed", "cancelled"].includes(job.status)) {
            setError(
              job.message ||
                "Re-summarization did not complete. Your previous summary is still available.",
            );
            setResummarizing(false);
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        } catch {
          /* Keep polling through temporary connection failures. */
        } finally {
          polling = false;
        }
      }, 3000);
    } catch (err) {
      console.error("Failed to start re-summarization:", err);
      setError(
        "Could not start re-summarization. Your previous summary is still available.",
      );
      setResummarizing(false);
    }
  }

  const getMarkdown = (): string => {
    if (!summary) return "";
    return summaryToMarkdown(summary, transcript?.duration);
  };

  const handleCopy = async () => {
    const md = getMarkdown();
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

  const handleDownloadMd = async () => {
    const md = getMarkdown();
    if (!md) return;
    setActionError("");
    try {
      const {downloadMarkdown} = await import('../lib/markdownDownload');
      downloadMarkdown(md, summary?.title || "summary");
    } catch { setActionError("Could not prepare Markdown download. Please retry."); }
  };

  const handleDownloadPdf = async () => {
    const md = getMarkdown();
    if (!md || pdfLoading) return;
    setActionError("");
    setPdfLoading(true);
    try {
      const { printPodcast } = await import("../lib/podcastPrint");
      await printPodcast(md, summary?.title || "Summary");
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

  function toggleTopic(topic: string) {
    const newExpanded = new Set(expandedTopics);
    if (newExpanded.has(topic)) {
      newExpanded.delete(topic);
    } else {
      newExpanded.add(topic);
    }
    setExpandedTopics(newExpanded);
  }

  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  const topicEntries = summaryChapters(summary);
  const introduction = summaryIntroduction(summary?.overview || "");

  const [activeSection, setActiveSection] = useState("summary-overview");
  useEffect(() => {
    if (loading || activeTab !== "summary") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    document
      .querySelectorAll(
        '[id^="summary-topic-"], #summary-conclusions, #summary-overview, #summary-key-points, #summary-takeaways',
      )
      .forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [summary, loading, activeTab]);

  const sections = [
    ...(introduction.conclusions
      ? [{ id: "summary-conclusions", title: "核心结论" }]
      : []),
    { id: "summary-overview", title: "Overview" },
    ...topicEntries.map(([topic], index) => ({
      id: `summary-topic-${index}`,
      title: topic,
    })),
    ...(summary?.takeaways.length
      ? [{ id: "summary-takeaways", title: "Takeaways" }]
      : []),
  ];
  const jumpToSection = (id: string) => {
    setActiveTab("summary");
    if (id.startsWith("summary-topic-")) {
      const topic = topicEntries[Number(id.replace("summary-topic-", ""))]?.[0];
      if (topic) setExpandedTopics((previous) => new Set([...previous, topic]));
    }
    setActiveSection(id);
    requestAnimationFrame(() =>
      document.getElementById(id)?.scrollIntoView({ block: "start" }),
    );
  };
  return (
    <ReaderFrame
      kind="Podcast"
      title={summary?.title || "Episode Viewer"}
      sections={
        activeTab === "summary" && !summary?.quality_warning ? sections : []
      }
      activeSection={activeSection}
      onNavigate={jumpToSection}
      metadata={
        <>
          {summary && (
            <>
              <span>{topicEntries.length} chapters</span>
              <span>{summary.key_points.length} key points</span>
            </>
          )}
          {transcript && <span>{formatTime(transcript.duration)}</span>}
        </>
      }
      actions={
        <>
          {summary && !summary.quality_warning && (
            <>
              <button
                className="reader-action"
                onClick={handleCopy}
                disabled={copying}
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
                <button onClick={handleDownloadMd} title="Download .md">
                  <Download size={16} />
                  Markdown
                </button>
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
                <a
                  href={`/api/summaries/${eid}/html${getAccessToken() ? `?token=${getAccessToken()}` : ""}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink size={16} />
                  Open as HTML
                </a>
              </ReaderMenu>
            </>
          )}
          <MoreReaderActions>
            <RegenerateAction
              onConfirm={() => void handleResummarize()}
              busy={resummarizing}
              disabled={
                !!summary?.quality_warning &&
                sourceBlocked(summary.source_status)
              }
            />
          </MoreReaderActions>
        </>
      }
      tabs={
        <>
          {(["summary", "transcript"] as const).map((tab) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              tabIndex={activeTab === tab ? 0 : -1}
              aria-controls={`podcast-${tab}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "summary" ? (
                <MessageSquare size={15} />
              ) : (
                <FileText size={15} />
              )}{" "}
              {tab === "summary" ? "Summary" : "Transcript"}
            </button>
          ))}
        </>
      }
    >
      {error && (
        <LoadError
          message={error}
          onRetry={() => {
            setError("");
            if (activeTab === "transcript") void loadTranscript();
            else void loadData();
          }}
        />
      )}
      {actionError && <div role="alert" className="text-sm text-red-300 mb-3">
        {actionError}{" "}<button className="underline" onClick={() => setActionError("")}>Dismiss</button>
      </div>}
      {loading && (
        <p role="status" className="reader-loading">
          <Loader2 size={18} className="animate-spin" />
          Loading summary…
        </p>
      )}
      {resummarizing && summary && (
        <p role="status" className="reader-loading">
          <Loader2 size={16} className="animate-spin" />
          Regenerating… Your saved summary remains available.
        </p>
      )}
      <div className="reader-body podcast-reader">
        {/* Content */}
        {activeTab === "transcript" && transcriptLoading && (
          <div role="status" className="flex justify-center py-12">
            <Loader2
              className="w-6 h-6 animate-spin text-indigo-500"
              aria-label="Loading transcript"
            />
          </div>
        )}
        {activeTab === "summary" && resummarizing && !summary && (
          <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
            <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
            <p className="text-lg text-white font-medium">
              Re-generating summary...
            </p>
            <p className="text-sm text-gray-400">
              This may take a minute. The page will update automatically when
              done.
            </p>
          </div>
        )}

        {summary?.quality_warning && (
          <SourceAccessNotice
            status={summary.source_status}
            message={summary.source_message}
            episodeId={eid}
            warning={summary.quality_warning}
          />
        )}
        {activeTab === "summary" && summary?.quality_warning && (
          <details className="text-sm text-gray-400">
            <summary className="cursor-pointer">
              Previous incomplete result
            </summary>
            <p className="mt-3">{summary.overview}</p>
          </details>
        )}
        {activeTab === "summary" && summary && !summary.quality_warning && (
          <div id="podcast-summary" role="tabpanel" className="space-y-6">
            {introduction.conclusions && (
              <section id="summary-conclusions" className="reader-core">
                <h2>核心结论</h2>
                <SummaryText>{introduction.conclusions}</SummaryText>
              </section>
            )}
            {/* Overview */}
            <div className="reader-section">
              <h2
                id="summary-overview"
                className="text-lg font-semibold text-white mb-4 flex items-center gap-2"
              >
                <FileText className="text-indigo-500" size={20} />
                Overview
              </h2>
              <SummaryText>{introduction.overview}</SummaryText>
            </div>

            {/* Topics/Key Points */}
            <section className="space-y-4">
              <h2
                id="summary-key-points"
                className="text-lg font-semibold text-white flex items-center gap-2"
              >
                <MessageSquare className="text-indigo-400" size={20} />
                Key Points by Topic
              </h2>

              <div className="flex gap-3 text-sm">
                <button
                  onClick={() =>
                    setExpandedTopics(
                      new Set(topicEntries.map(([topic]) => topic)),
                    )
                  }
                >
                  Expand all
                </button>
                <button onClick={() => setExpandedTopics(new Set())}>
                  Collapse all
                </button>
              </div>
              <div className="space-y-3" data-topic-column>
                {topicEntries.map(([topic, points], index) => (
                  <div
                    key={topic}
                    data-topic-card
                    id={`summary-topic-${index}`}
                    aria-current={
                      activeSection === `summary-topic-${index}`
                        ? "location"
                        : undefined
                    }
                    className="topic-section"
                  >
                    <button
                      onClick={() => toggleTopic(topic)}
                      aria-expanded={expandedTopics.has(topic)}
                      aria-controls={`summary-topic-content-${index}`}
                      className="topic-toggle w-full flex items-center justify-between gap-3"
                    >
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0 text-left">
                        <span className="topic-number" aria-hidden="true">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="font-medium text-white">{topic}</span>
                        <span className="text-sm text-gray-500">
                          ({points.length} points)
                        </span>
                      </div>
                      {expandedTopics.has(topic) ? (
                        <ChevronUp size={20} className="text-gray-400" />
                      ) : (
                        <ChevronDown size={20} className="text-gray-400" />
                      )}
                    </button>

                    {expandedTopics.has(topic) && (
                      <div
                        id={`summary-topic-content-${index}`}
                        className="topic-content space-y-4"
                      >
                        {points.map((kp, idx) => (
                          <div key={idx} className="reader-point space-y-3">
                            <SummaryText>{kp.summary}</SummaryText>
                            {kp.original_quote && (
                              <details className="reader-quote">
                                <summary>
                                  <Quote size={14} aria-hidden="true" />
                                  查看转写原话
                                  {kp.timestamp && (
                                    <span> · {kp.timestamp}</span>
                                  )}
                                </summary>
                                <blockquote>{kp.original_quote}</blockquote>
                              </details>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* Takeaways */}
            {summary.takeaways.length > 0 && (
              <div className="reader-section">
                <h2
                  id="summary-takeaways"
                  className="text-lg font-semibold text-white mb-4 flex items-center gap-2"
                >
                  <CheckCircle className="text-green-500" size={20} />
                  Takeaways
                </h2>
                <ul className="space-y-3">
                  {summary.takeaways.map((takeaway: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-3">
                      <CheckCircle
                        className="text-green-500 flex-shrink-0 mt-0.5"
                        size={16}
                      />
                      <SummaryText>{takeaway}</SummaryText>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {activeTab === "transcript" && transcript && (
          <div
            id="podcast-transcript"
            role="tabpanel"
            className="reader-section"
          >
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <FileText className="text-blue-500" size={20} />
              Full Transcript
            </h2>

            {transcript.segments.length > 0 ? (
              <TranscriptSegments
                key={eid}
                segments={transcript.segments}
                text={transcript.text}
                fallback={
                  <p className="whitespace-pre-wrap">{transcript.text}</p>
                }
              />
            ) : (
              <p className="text-gray-300 whitespace-pre-line leading-relaxed">
                {transcript.text}
              </p>
            )}
          </div>
        )}

        {!loading && !summary && !transcript && !error && (
          <div className="p-12 bg-dark-surface border border-dark-border rounded-xl text-center">
            <FileText className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-xl text-gray-400 mb-2">No content available</p>
            <p className="text-gray-500">
              Process this episode to generate transcript and summary
            </p>
          </div>
        )}

        {notionOpen && summary && (
          <PodcastNotionExport
            summary={summary}
            duration={transcript?.duration}
            onClose={() => setNotionOpen(false)}
            fallback={<p role="status">Loading export…</p>}
          />
        )}
      </div>
    </ReaderFrame>
  );
}
