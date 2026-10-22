import { useEffect, useRef, useState } from "react";
import { getCache, hydrateCache, setCache, useWarmCache } from "./cache";
import { getAccountId } from "./preferences";
import { fetchLibrary, type LibraryItem } from "./api";

export type ReadingEntry = {
  id: string;
  kind: "podcast" | "video";
  title: string;
  source?: string;
  thumbnail?: string;
  lastRead: number;
  progress: number;
  position?: number;
};
const KEY = "reading_history";
export function useReadingHistory() {
  const [history, setHistory] = useState<ReadingEntry[]>(
    () => getCache(KEY) || [],
  );
  useWarmCache<ReadingEntry[]>(KEY, setHistory);
  return history;
}

/** Record visits only after a readable note appears, never during prefetch. */
export function useRecordReading(
  entry: Omit<ReadingEntry, "lastRead" | "progress">,
  ready: boolean,
  elementId?: string,
) {
  const value = useRef(entry);
  value.current = entry;
  useEffect(() => {
    if (!ready) return;
    const owner = getAccountId();
    const el = elementId
      ? document.getElementById(elementId)
      : document.querySelector("main");
    if (!el) return;
    let active = true,
      timer: ReturnType<typeof setTimeout> | undefined;
    const snapshot = () => {
      const range = el.scrollHeight - el.clientHeight;
      return {
        position: el.scrollTop,
        progress:
          range > 0
            ? Math.min(100, Math.round((el.scrollTop / range) * 100))
            : 0,
      };
    };
    let position = snapshot();
    const save = () => {
      if (!active || owner !== getAccountId() || document.hidden) return;
      const history = getCache<ReadingEntry[]>(KEY) || [];
      const metadata =
        value.current.id === entry.id && value.current.kind === entry.kind
          ? value.current
          : entry;
      setCache(
        KEY,
        [
          { ...metadata, lastRead: Date.now(), ...position },
          ...history.filter((r) => r.id !== entry.id || r.kind !== entry.kind),
        ].slice(0, 30),
        owner,
      );
    };
    void hydrateCache(KEY).then(() => {
      if (active) {
        position = snapshot();
        save();
      }
    });
    const scroll = () => {
      position = snapshot();
      clearTimeout(timer);
      timer = setTimeout(save, 750);
    };
    el.addEventListener("scroll", scroll, { passive: true });
    return () => {
      clearTimeout(timer);
      save();
      active = false;
      el.removeEventListener("scroll", scroll);
    };
  }, [entry.id, entry.kind, ready, elementId]);
}

/** Revalidate saved browser references against the owned, readable library. */
export function useVerifiedReading() {
  const history = useReadingHistory();
  const [items, setItems] = useState<(LibraryItem & ReadingEntry)[]>([]);
  const [status, setStatus] = useState<"ready" | "loading" | "error">("ready");
  const [attempt, setAttempt] = useState(0);
  const signature = history.map((r) => `${r.kind}:${r.id}`).join(",");
  useEffect(() => {
    if (!signature) {
      setItems([]);
      setStatus("ready");
      return;
    }
    setItems([]);
    setStatus("loading");
    let active = true;
    const owner = getAccountId();
    const abort = new AbortController();
    void fetchLibrary(
      new URLSearchParams({ ids: signature, limit: "30" }).toString(),
      "",
      abort.signal,
    )
      .then((page) => {
        if (active && owner === getAccountId()) {
          setItems(
            history.flatMap((entry) => {
              const item = page.items.find(
                (i) => i.kind === entry.kind && i.id === entry.id,
              );
              return item ? [{ ...entry, ...item }] : [];
            }),
          );
          setStatus("ready");
        }
      })
      .catch(() => {
        if (active && owner === getAccountId()) setStatus("error");
      });
    return () => {
      active = false;
      abort.abort();
    };
  }, [signature, attempt]);
  return {
    items: items.map((item) => ({
      ...item,
      progress:
        history.find((h) => h.kind === item.kind && h.id === item.id)
          ?.progress || 0,
    })),
    status,
    retry: () => setAttempt((value) => value + 1),
  };
}
