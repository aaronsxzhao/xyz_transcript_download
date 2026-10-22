// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { deferView } from "../src/components/DeferredView";
let cleanup = () => {};
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
it("bounds a stalled optional chunk and retries without losing the page", async () => {
  vi.useFakeTimers();
  vi.spyOn(console, "error").mockImplementation(() => {});
  const load = vi
    .fn()
    .mockImplementationOnce(() => new Promise(() => {}))
    .mockResolvedValueOnce({ default: () => <p>Interactive map</p> });
  const View = deferView(load);
  const node = document.createElement("div");
  document.body.append(node);
  const root = createRoot(node);
  cleanup = () => {
    act(() => root.unmount());
    node.remove();
  };
  await act(async () =>
    root.render(
      <>
        <h1>Saved summary stays available</h1>
        <View fallback={<p>Preparing tool</p>} />
      </>,
    ),
  );
  expect(load).toHaveBeenCalledOnce();
  await act(async () => vi.advanceTimersByTimeAsync(15000));
  expect(node.textContent).toContain("Saved summary stays available");
  const retry = [...node.querySelectorAll("button")].find(
    (button) => button.textContent === "Retry loading",
  )!;
  expect(retry).toBeTruthy();
  await act(async () => retry.click());
  expect(load).toHaveBeenCalledTimes(2);
  expect(node.textContent).toContain("Interactive map");
  expect(node.textContent).not.toContain("Formatting could not load");
});
