// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});
it("hydrates only the requested body before idle maintenance and ignores a late account response", async () => {
  vi.resetModules();
  vi.useFakeTimers();
  localStorage.clear();
  sessionStorage.clear();
  const requests: { name: string; request: any }[] = [];
  const cursor = vi.fn();
  const db = {
    transaction: () => ({
      objectStore: () => ({
        get: (name: string) => {
          const request = {
            result: undefined,
            onsuccess: undefined as any,
            onerror: undefined,
          };
          requests.push({ name, request });
          return request;
        },
        openCursor: cursor,
        put: vi.fn(),
        delete: vi.fn(),
      }),
    }),
  };
  vi.stubGlobal("indexedDB", {
    open: () => {
      const request = { result: db, onsuccess: undefined as any };
      queueMicrotask(() => request.onsuccess?.());
      return request;
    },
  });
  const { hydrateCache, getCache } = await import("../src/lib/cache");
  const first = hydrateCache("summary_requested");
  await vi.waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0].name).toBe("xyz_cache_local:summary_requested");
  expect(cursor).not.toHaveBeenCalled();
  requests[0].request.result = {
    key: requests[0].name,
    data: "Requested body",
    timestamp: Date.now(),
    accessed: Date.now(),
    bytes: 28,
  };
  requests[0].request.onsuccess();
  await first;
  expect(getCache("summary_requested")).toBe("Requested body");
  const late = hydrateCache("summary_other");
  await vi.waitFor(() => expect(requests).toHaveLength(2));
  localStorage.setItem(
    "xyz_user",
    JSON.stringify({ id: "other", authenticated: true }),
  );
  requests[1].request.result = {
    key: requests[1].name,
    data: "Previous account private body",
    timestamp: Date.now(),
    accessed: Date.now(),
    bytes: 80,
  };
  requests[1].request.onsuccess();
  await late;
  expect(getCache("summary_other")).toBeNull();
  expect(cursor).not.toHaveBeenCalled();
});

it("continues without disk cache when IndexedDB opening stalls", async () => {
  vi.resetModules();
  vi.useFakeTimers();
  vi.stubGlobal("indexedDB", { open: () => ({}) });
  const { hydrateCache, setCache, getCache } = await import("../src/lib/cache");
  let done = false;
  void hydrateCache("summary_network").then(() => {
    done = true;
  });
  await vi.advanceTimersByTimeAsync(1001);
  expect(done).toBe(true);
  setCache("summary_network", "Fresh network body");
  expect(getCache("summary_network")).toBe("Fresh network body");
});

it("bounds stalled transactions and does not replace fresh data with a late disk read", async () => {
  vi.resetModules();
  vi.useFakeTimers();
  const read: any = {};
  const db = {
    transaction: () => ({
      objectStore: () => ({ get: () => read, put: vi.fn() }),
    }),
  };
  vi.stubGlobal("indexedDB", {
    open: () => {
      const request = { result: db, onsuccess: undefined as any };
      queueMicrotask(() => request.onsuccess?.());
      return request;
    },
  });
  const { hydrateCache, setCache, getCache } = await import("../src/lib/cache");
  let done = false;
  void hydrateCache("summary_network").then(() => {
    done = true;
  });
  await vi.advanceTimersByTimeAsync(1001);
  expect(done).toBe(true);
  setCache("summary_network", "Fresh network body");
  read.result = {
    key: "xyz_cache_local:summary_network",
    data: "Stale disk body",
    timestamp: Date.now(),
    accessed: Date.now(),
    bytes: 30,
  };
  read.onsuccess();
  await Promise.resolve();
  expect(getCache("summary_network")).toBe("Fresh network body");
});
