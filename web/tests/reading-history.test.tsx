// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { getCache, setCache, clearCache } from "../src/lib/cache";
import * as cache from "../src/lib/cache";
import {
  useRecordReading,
  useVerifiedReading,
  type ReadingEntry,
} from "../src/lib/readingHistory";
import { fetchLibrary } from "../src/lib/api";
vi.mock("../src/lib/api", async (load) => ({
  ...(await load<object>()),
  fetchLibrary: vi.fn(),
}));
let root: ReturnType<typeof createRoot>, node: HTMLElement;
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  clearCache();
  node = document.createElement("main");
  document.body.append(node);
  root = createRoot(node);
  vi.clearAllMocks();
});
afterEach(() => {
  act(() => root.unmount());
  node.remove();
  clearCache();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("flushes the latest position when the reader backgrounds before the scroll debounce", async () => {
  vi.useFakeTimers();
  let hidden = false;
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  Object.defineProperty(node, 'scrollHeight', {value: 2000, configurable: true});
  Object.defineProperty(node, 'clientHeight', {value: 1000, configurable: true});
  await act(async () => root.render(<Reader ready />));
  node.scrollTop = 650;
  node.dispatchEvent(new Event('scroll'));
  hidden = true;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(getCache<ReadingEntry[]>('reading_history')?.[0]).toMatchObject({position: 650, progress: 65});
  // Layout clamping in the hidden tab must not replace the last read position.
  node.scrollTop = 0;
  node.dispatchEvent(new Event('scroll'));
  await act(async () => window.dispatchEvent(new Event('pagehide')));
  expect(getCache<ReadingEntry[]>('reading_history')?.[0].position).toBe(650);
});

it("does not mark content read until its tab has actually been visible", async () => {
  let hidden = true;
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  await act(async () => root.render(<Reader ready />));
  await act(async () => window.dispatchEvent(new Event('pagehide')));
  expect(getCache('reading_history')).toBeNull();
  hidden = false;
  node.scrollTop = 420;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  expect(getCache<ReadingEntry[]>('reading_history')?.[0]).toMatchObject({id: 'one', position: 420});
});

it("does not let late cache hydration overwrite the saved background position", async () => {
  let finish!: () => void, hidden = false;
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  vi.spyOn(cache, 'hydrateCache').mockImplementationOnce(() => new Promise(resolve => {finish = resolve}));
  await act(async () => root.render(<Reader ready />));
  node.scrollTop = 650;
  node.dispatchEvent(new Event('scroll'));
  hidden = true;
  await act(async () => document.dispatchEvent(new Event('visibilitychange')));
  node.scrollTop = 0;
  await act(async () => finish());
  expect(getCache<ReadingEntry[]>('reading_history')?.[0].position).toBe(650);
});
function Reader({ ready }: { ready: boolean }) {
  useRecordReading({ id: "one", kind: "podcast", title: "Saved note" }, ready);
  return <p>Note</p>;
}
function History() {
  const { items } = useVerifiedReading();
  return <p>{items.map((i) => i.title).join(",")}</p>;
}
it("records actual readable visits, not pending or invalid pages", async () => {
  await act(async () => root.render(<Reader ready={false} />));
  expect(getCache("reading_history")).toBeNull();
  await act(async () => root.render(<Reader ready />));
  expect(getCache<ReadingEntry[]>("reading_history")?.[0]).toMatchObject({
    id: "one",
    kind: "podcast",
    title: "Saved note",
    position: 0,
  });
});
it("verifies ownership and readiness before showing saved history", async () => {
  setCache("reading_history", [
    {
      id: "one",
      kind: "podcast",
      title: "Old title",
      progress: 35,
      lastRead: 10,
    },
    {
      id: "missing",
      kind: "video",
      title: "Unavailable",
      progress: 2,
      lastRead: 9,
    },
  ]);
  vi.mocked(fetchLibrary).mockResolvedValue({
    items: [
      {
        id: "one",
        kind: "podcast",
        title: "Verified note",
        source: "Show",
        date: "",
        status: "completed",
      },
    ],
    next_cursor: null,
  });
  await act(async () => root.render(<History />));
  expect(node.textContent).toBe("Verified note");
  expect(node.textContent).not.toContain("Unavailable");
  expect(fetchLibrary).toHaveBeenCalledWith(
    expect.stringContaining("ids=podcast%3Aone%2Cvideo%3Amissing"),
    "",
    expect.any(AbortSignal),
  );
});

it("offers recovery when reading references cannot be verified", async () => {
  setCache("reading_history", [
    {
      id: "one",
      kind: "podcast",
      title: "Old note",
      progress: 12,
      lastRead: 10,
    },
  ]);
  vi.mocked(fetchLibrary)
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValueOnce({ items: [], next_cursor: null });
  function Status() {
    const { status, retry } = useVerifiedReading();
    return (
      <>
        <p>{status}</p>
        <button onClick={retry}>Retry history</button>
      </>
    );
  }
  await act(async () => root.render(<Status />));
  expect(node.textContent).toContain("error");
  await act(async () => node.querySelector("button")!.click());
  expect(node.textContent).toContain("ready");
  expect(fetchLibrary).toHaveBeenCalledTimes(2);
});

it("preserves the last summary progress when a tab replacement shrinks the DOM", async () => {
  Object.defineProperty(node, "scrollHeight", {
    value: 2000,
    configurable: true,
  });
  Object.defineProperty(node, "clientHeight", {
    value: 1000,
    configurable: true,
  });
  await act(async () => root.render(<Reader ready />));
  node.scrollTop = 800;
  node.dispatchEvent(new Event("scroll"));
  node.scrollTop = 0;
  Object.defineProperty(node, "scrollHeight", {
    value: 1000,
    configurable: true,
  });
  await act(async () => root.render(<Reader ready={false} />));
  expect(getCache<ReadingEntry[]>("reading_history")?.[0]).toMatchObject({
    position: 800,
    progress: 80,
  });
});

it("does not mix entry identities while navigating between readers", async () => {
  function Note({ id }: { id: string }) {
    useRecordReading({ id, kind: "podcast", title: id }, true);
    return <p>{id}</p>;
  }
  await act(async () => root.render(<Note id="first" />));
  node.scrollTop = 400;
  node.dispatchEvent(new Event("scroll"));
  await act(async () => root.render(<Note id="second" />));
  const history = getCache<ReadingEntry[]>("reading_history")!;
  expect(history.filter((row) => row.id === "second")).toHaveLength(1);
  expect(history.find((row) => row.id === "first")).toMatchObject({
    title: "first",
    position: 400,
  });
});
