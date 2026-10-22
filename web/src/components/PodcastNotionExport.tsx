import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import {
  ExternalLink,
  Loader2,
  Search,
  X,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import { useDialog } from "../lib/reading";
import { getPreference } from "../lib/preferences";
import {
  fetchNotionPages,
  exportMarkdownToNotion,
  type Summary,
  type VideoTask,
  type NotionPage,
} from "../lib/api";
import { buildNotionExportMarkdown } from "../lib/notionExport";
import { summaryToMarkdown } from "../lib/summaryReading";

export default function PodcastNotionExport({
  summary,
  duration,
  task,
  content,
  onClose,
}: {
  summary?: Summary;
  duration?: number;
  task?: VideoTask;
  content?: string;
  onClose: () => void;
}) {
  useDialog(true, onClose);
  const [notionPages, setNotionPages] = useState<NotionPage[]>([]);
  const [notionSearch, setNotionSearch] = useState("");
  const [notionLoading, setNotionLoading] = useState(false);
  const [notionExporting, setNotionExporting] = useState(false);
  const [notionSelectedId, setNotionSelectedId] = useState("");
  const [notionResult, setNotionResult] = useState<{
    ok: boolean;
    message: string;
    url?: string;
  } | null>(null);
  const notionSearchTimeout = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  const request = useRef(0);
  const hasNotionKey = !!getPreference("notion_api_key");

  const openNotionModal = useCallback(async () => {
    const attempt = ++request.current;
    setNotionResult(null);
    setNotionSelectedId("");
    setNotionSearch("");
    setNotionLoading(true);
    try {
      const data = await fetchNotionPages();
      if (attempt === request.current) setNotionPages(data.pages);
    } catch (err) {
      if (attempt === request.current)
        setNotionResult({
          ok: false,
          message: err instanceof Error ? err.message : "Failed to load pages",
        });
    } finally {
      if (attempt === request.current) setNotionLoading(false);
    }
  }, []);

  const handleNotionSearch = useCallback((q: string) => {
    const attempt = ++request.current;
    setNotionSearch(q);
    setNotionLoading(true);
    setNotionResult(null);
    setNotionSelectedId("");
    if (notionSearchTimeout.current) clearTimeout(notionSearchTimeout.current);
    notionSearchTimeout.current = setTimeout(async () => {
      setNotionLoading(true);
      try {
        const data = await fetchNotionPages(q || undefined);
        if (attempt === request.current) setNotionPages(data.pages);
      } catch (err) {
        if (attempt === request.current)
          setNotionResult({
            ok: false,
            message:
              err instanceof Error ? err.message : "Failed to load pages",
          });
      } finally {
        if (attempt === request.current) setNotionLoading(false);
      }
    }, 400);
  }, []);

  const handleNotionExport = useCallback(async () => {
    if ((!summary && !task) || !notionSelectedId) return;
    setNotionExporting(true);
    setNotionResult(null);
    try {
      const md = summary
        ? summaryToMarkdown(summary, duration)
        : buildNotionExportMarkdown(task!, content || "");
      const result = await exportMarkdownToNotion(
        md,
        summary?.title || task?.title || "Untitled Video Note",
        notionSelectedId,
      );
      setNotionResult({
        ok: true,
        message: `Exported "${result.title}" to Notion`,
        url: result.url,
      });
    } catch (err) {
      setNotionResult({
        ok: false,
        message: err instanceof Error ? err.message : "Export failed",
      });
    } finally {
      setNotionExporting(false);
    }
  }, [notionSelectedId, summary, duration, task, content]);

  useEffect(() => {
    if (hasNotionKey) void openNotionModal();
    return () => {
      request.current++;
      if (notionSearchTimeout.current)
        clearTimeout(notionSearchTimeout.current);
    };
  }, [openNotionModal, hasNotionKey]);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Export to Notion"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-dark-surface border border-dark-border rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-dark-border">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <ExternalLink size={16} />
            Send to Notion
          </h2>
          <button
            aria-label="Close Notion export"
            onClick={() => onClose()}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {!hasNotionKey ? (
            <div className="space-y-3 py-2">
              <p className="text-sm text-gray-300">
                Set up your Notion integration to export summaries.
              </p>
              <ol className="text-xs text-gray-400 space-y-1.5 list-decimal list-inside">
                <li>
                  Go to{" "}
                  <a
                    href="https://www.notion.so/profile/integrations"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-orange-400 hover:text-orange-300"
                  >
                    Notion Integrations{" "}
                    <ExternalLink size={10} className="inline" />
                  </a>
                </li>
                <li>Create an integration and copy the token</li>
                <li>
                  Go to{" "}
                  <Link
                    to="/settings"
                    className="text-orange-400 hover:text-orange-300"
                  >
                    Settings
                  </Link>{" "}
                  and paste it in the Notion section
                </li>
                <li>Share target pages with your integration in Notion</li>
              </ol>
            </div>
          ) : (
            <>
              <div className="relative">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                />
                <input
                  type="text"
                  value={notionSearch}
                  onChange={(e) => handleNotionSearch(e.target.value)}
                  placeholder="Search pages..."
                  className="w-full pl-9 pr-3 py-2 bg-dark-hover border border-dark-border text-white text-sm rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                  autoFocus
                />
              </div>

              <div className="max-h-60 overflow-y-auto custom-scrollbar space-y-0.5">
                {notionLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 size={20} className="animate-spin text-gray-500" />
                  </div>
                ) : notionPages.length === 0 ? (
                  <div className="text-center py-8 text-sm text-gray-500">
                    {notionResult?.ok === false
                      ? "Could not load pages"
                      : "No pages found. Share pages with your integration in Notion."}
                  </div>
                ) : (
                  notionPages.map((page) => (
                    <button
                      key={page.id}
                      onClick={() =>
                        setNotionSelectedId(
                          page.id === notionSelectedId ? "" : page.id,
                        )
                      }
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left text-sm transition-colors ${
                        page.id === notionSelectedId
                          ? "bg-orange-500/15 border border-orange-500/40 text-white"
                          : "hover:bg-dark-hover text-gray-300 border border-transparent"
                      }`}
                    >
                      <span className="flex-shrink-0 w-5 text-center">
                        {page.icon || "📄"}
                      </span>
                      <span className="truncate flex-1">
                        {page.title || "Untitled"}
                      </span>
                      {page.id === notionSelectedId && (
                        <CheckCircle
                          size={14}
                          className="text-orange-400 flex-shrink-0"
                        />
                      )}
                    </button>
                  ))
                )}
              </div>
            </>
          )}

          {notionResult && (
            <div
              className={`p-2.5 rounded-lg text-xs ${
                notionResult.ok
                  ? "bg-green-500/10 border border-green-500/30 text-green-400"
                  : "bg-red-500/10 border border-red-500/30 text-red-400"
              }`}
            >
              {notionResult.ok ? (
                <CheckCircle size={12} className="inline mr-1.5" />
              ) : (
                <AlertTriangle size={12} className="inline mr-1.5" />
              )}
              {notionResult.message}
              {notionResult.url && (
                <a
                  href={notionResult.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-2 inline-flex items-center gap-1 text-orange-400 hover:text-orange-300"
                >
                  Open in Notion <ExternalLink size={10} />
                </a>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-dark-border">
          <button
            aria-label="Close Notion export"
            onClick={() => onClose()}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            {notionResult?.ok ? "Done" : hasNotionKey ? "Cancel" : "Close"}
          </button>
          {hasNotionKey && !notionResult?.ok && (
            <button
              onClick={handleNotionExport}
              disabled={!notionSelectedId || notionExporting}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {notionExporting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ExternalLink size={14} />
              )}
              Export
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
