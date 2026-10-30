// @vitest-environment jsdom
import React, { act, lazy } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { deferView, OptionalTool } from "../src/components/DeferredView";
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

it('keeps recovery controls inside a custom modal fallback', async () => {
  vi.useFakeTimers();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const load=vi.fn().mockImplementationOnce(()=>new Promise(()=>{})).mockResolvedValueOnce({default:()=> <p>Confirmation ready</p>});
  const View=deferView(load);
  const node=document.createElement('div');document.body.append(node);const root=createRoot(node);
  cleanup=()=>{act(()=>root.unmount());node.remove()};
  await act(async()=>root.render(<View fallback={<section role="dialog">Loading confirmation</section>} errorFallback={retry=><section role="dialog"><button onClick={retry}>Retry confirmation</button></section>}/>));
  await act(async()=>vi.advanceTimersByTimeAsync(15000));
  expect(node.querySelectorAll('button')).toHaveLength(1);
  const retry=node.querySelector('[role="dialog"] button') as HTMLButtonElement;
  expect(retry).toBeTruthy();
  await act(async()=>retry.click());
  expect(node.textContent).toBe('Confirmation ready');
});

it.each([false,true])('bounds optional tools and preserves the page (custom fallback: %s)', async custom => {
  vi.useFakeTimers();vi.spyOn(console,'error').mockImplementation(()=>{});
  const Tool=lazy(()=>new Promise<{default:()=>React.ReactNode}>(()=>{}));
  const node=document.createElement('div');document.body.append(node);const root=createRoot(node);
  cleanup=()=>{act(()=>root.unmount());node.remove()};
  await act(async()=>root.render(<><h1>Saved note</h1><OptionalTool fallback={<p>Loading image controls</p>} errorFallback={custom?<section role="dialog">Original image<button>Close</button></section>:undefined}><Tool/></OptionalTool></>));
  await act(async()=>vi.advanceTimersByTimeAsync(14999));
  expect(node.textContent).toContain('Loading image controls');
  await act(async()=>vi.advanceTimersByTimeAsync(1));
  expect(node.textContent).toContain('Saved note');
  expect(node.textContent).not.toContain('Loading image controls');
  expect(node.textContent).toContain(custom?'Original image':'Reload tools');
});

it('cleans up the pending deadline when an optional tool finishes loading', async () => {
  vi.useFakeTimers();
  let resolve!:(module:{default:()=>React.ReactNode})=>void;
  const Tool=lazy(()=>new Promise<{default:()=>React.ReactNode}>(done=>{resolve=done}));
  const node=document.createElement('div');document.body.append(node);const root=createRoot(node);
  cleanup=()=>{act(()=>root.unmount());node.remove()};
  await act(async()=>root.render(<OptionalTool fallback={<p>Loading</p>}><Tool/></OptionalTool>));
  await act(async()=>resolve({default:()=> <p>Tool ready</p>}));
  await act(async()=>vi.advanceTimersByTimeAsync(20000));
  expect(node.textContent).toBe('Tool ready');
});
