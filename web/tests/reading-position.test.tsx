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
it.each([null, '0'])("opens at the top instead of inheriting another page's scroll when saved position is %s", async saved => {
  if (saved !== null) sessionStorage.setItem('xyz_reading:local:video:one', saved);
  node.scrollTop = 860;
  await act(async () => root.render(<Reader />));
  expect(node.scrollTop).toBe(0);
});
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

it.each(['keyboard','pointer'])('stops restoring when the reader navigates by %s while content is still growing', async mode => {
  let resize!:()=>void, maximum=50, position=0;
  vi.stubGlobal('ResizeObserver',class {
    constructor(callback:()=>void){resize=callback}
    observe(){}
    disconnect(){}
  });
  Object.defineProperty(node,'scrollTop',{
    configurable:true,get:()=>position,set:(value:number)=>{position=Math.min(value,maximum)},
  });
  sessionStorage.setItem('xyz_reading:local:video:one','860');
  await act(async()=>root.render(<Reader/>));
  expect(node.scrollTop).toBe(50);
  node.dispatchEvent(mode==='keyboard'?new KeyboardEvent('keydown',{key:'PageDown',bubbles:true}):new Event('pointerdown',{bubbles:true}));
  node.scrollTop=20;
  node.dispatchEvent(new Event('scroll'));
  maximum=2000;resize();
  expect(node.scrollTop).toBe(20);
  expect(sessionStorage.getItem('xyz_reading:local:video:one')).toBe('20');
});

it('defers resize restoration to a frame and respects navigation before it runs', async () => {
  let resize!:()=>void, frame!:FrameRequestCallback, maximum=50, position=0;
  vi.stubGlobal('ResizeObserver',class {
    constructor(callback:()=>void){resize=callback}
    observe(){}
    disconnect(){}
  });
  const request=vi.fn((callback:FrameRequestCallback)=>{frame=callback;return 7});
  const cancel=vi.fn();
  vi.stubGlobal('requestAnimationFrame',request);
  vi.stubGlobal('cancelAnimationFrame',cancel);
  Object.defineProperty(node,'scrollTop',{
    configurable:true,get:()=>position,set:(value:number)=>{position=Math.min(value,maximum)},
  });
  sessionStorage.setItem('xyz_reading:local:video:one','860');
  await act(async()=>root.render(<Reader/>));
  maximum=2000;
  resize();resize();
  expect(node.scrollTop).toBe(50); // No layout writes during observer delivery.
  expect(request).toHaveBeenCalledTimes(1);
  frame(0);
  expect(node.scrollTop).toBe(860);

  await act(async()=>root.render(<Reader ready={false}/>));
  maximum=50;
  await act(async()=>root.render(<Reader/>));
  maximum=2000;resize();
  node.dispatchEvent(new KeyboardEvent('keydown',{key:'PageDown',bubbles:true}));
  node.scrollTop=20;node.dispatchEvent(new Event('scroll'));
  frame(0);
  expect(node.scrollTop).toBe(20);
  await act(async()=>root.render(<Reader ready={false}/>));
  expect(cancel).toHaveBeenCalled();
});
