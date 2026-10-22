// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRecordReading } from "../src/lib/readingHistory";
import { getCache, setCache } from "../src/lib/cache";
import { useReadingPosition } from "../src/lib/reading";
let node: HTMLElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  node = document.createElement("main");
  document.body.append(node);
  root = createRoot(node);
});
afterEach(() => {
  act(() => root.unmount());
  node.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function Reader({ ready = true }: { ready?: boolean }) {
  useReadingPosition("video:one", undefined, ready);
  return <article>Summary</article>;
}
it("keeps the last summary position when the DOM shrinks during a tab switch", async () => {
  await act(async () => root.render(<Reader />));
  node.scrollTop = 860;
  node.dispatchEvent(new Event("scroll"));
  node.scrollTop = 0; // replacing a long summary with a short map clamps the scroll before effect cleanup
  await act(async () => root.render(<Reader ready={false} />));
  expect(sessionStorage.getItem("xyz_reading:local:video:one")).toBe("860");
  node.scrollTop = 100;
  node.dispatchEvent(new Event("scroll"));
  expect(sessionStorage.getItem("xyz_reading:local:video:one")).toBe("860");
  await act(async () => root.render(<Reader />));
  expect(node.scrollTop).toBe(860);
});
it("still renders when sessionStorage is unavailable", async () => {
  const get = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
    this: Storage,
    key: string,
  ) {
    if (key.startsWith("xyz_reading:"))
      throw new DOMException("Blocked", "SecurityError");
    return get.call(this, key);
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Full", "QuotaExceededError");
  });
  await act(async () => root.render(<Reader />));
  node.scrollTop = 20;
  node.dispatchEvent(new Event("scroll"));
  expect(node.textContent).toBe("Summary");
});

it("records the restored position after asynchronous history hydration", async () => {
  setCache("reading_history", [
    {
      id: "one",
      kind: "video",
      title: "Old title",
      position: 860,
      progress: 86,
      lastRead: 1,
    },
  ]);
  Object.defineProperty(node, "scrollHeight", {
    value: 2000,
    configurable: true,
  });
  Object.defineProperty(node, "clientHeight", {
    value: 1000,
    configurable: true,
  });
  function Restored() {
    useReadingPosition("video:one");
    useRecordReading(
      { id: "one", kind: "video", title: "Current title" },
      true,
    );
    return <article>Note</article>;
  }
  await act(async () => root.render(<Restored />));
  expect(node.scrollTop).toBe(860);
  expect(
    getCache<{ position: number }[]>("reading_history")?.[0].position,
  ).toBe(860);
});
