// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NotionExport from "../src/components/PodcastNotionExport";
import {
  ApiError,
  fetchNotionPages,
  exportMarkdownToNotion,
  type Summary,
  type VideoTask,
} from "../src/lib/api";
vi.mock("../src/lib/api", async load => ({
  ...await load<object>(),
  fetchNotionPages: vi.fn(),
  exportMarkdownToNotion: vi.fn(),
}));
vi.mock("../src/lib/reading", () => ({ useDialog: vi.fn() }));
let node: HTMLElement, root: ReturnType<typeof createRoot>;
const summary: Summary = {
  episode_id: "one",
  title: "Podcast note",
  overview: "Source detail",
  topics: [],
  key_points: [],
  takeaways: [],
};
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("xyz_pref:local:notion_api_key", "private-test-key");
  node = document.createElement("div");
  document.body.append(node);
  root = createRoot(node);
});
afterEach(() => {
  act(() => root.unmount());
  node.remove();
  vi.useRealTimers();
});
function type(value: string) {
  const input = node.querySelector("input")!;
  Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )!.set!.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
const button=(label:string)=>[...node.querySelectorAll('button')].find(item=>item.textContent?.trim()===label)!;
async function readyToExport(){
 vi.mocked(fetchNotionPages).mockResolvedValue({pages:[{id:'target',title:'Notebook'}]} as any);
 await act(async()=>root.render(<MemoryRouter><NotionExport summary={summary} onClose={()=>{}}/></MemoryRouter>));
 await act(async()=>button('📄Notebook').click());
}
it('locks the destination during export and preserves the success receipt',async()=>{
 let finish!:(value:any)=>void;
 vi.mocked(exportMarkdownToNotion).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
 await readyToExport();await act(async()=>button('Export').click());
 expect(node.querySelector('input')!.disabled).toBe(true);
 expect(button('📄Notebook').disabled).toBe(true);
 await act(async()=>finish({title:'Saved',url:'https://notion.so/saved'}));
 expect(node.querySelector('input')!.disabled).toBe(true);
 expect(node.querySelector('[role=status]')?.textContent).toContain('Exported "Saved"');
 expect(button('Export')).toBeUndefined();
});
it('does not offer immediate resubmission after an unconfirmed export',async()=>{
 vi.mocked(exportMarkdownToNotion).mockRejectedValueOnce(new Error('No confirmation received'));
 await readyToExport();await act(async()=>button('Export').click());
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Check Notion');
 expect(button('Export')).toBeUndefined();
});
it('submits only once even when two clicks arrive before React renders the pending state',async()=>{
 vi.mocked(exportMarkdownToNotion).mockImplementationOnce(()=>new Promise(()=>{}));
 await readyToExport();const submit=button('Export');
 await act(async()=>{submit.click();submit.click()});
 expect(exportMarkdownToNotion).toHaveBeenCalledOnce();
});
it('allows correcting a rejected destination before any page was created',async()=>{
 vi.mocked(exportMarkdownToNotion).mockRejectedValueOnce(new ApiError('Invalid Notion API key',401));
 await readyToExport();await act(async()=>button('Export').click());
 expect(node.querySelector('[role=alert]')?.textContent).toContain('Invalid Notion API key');
 expect(node.querySelector('input')!.disabled).toBe(false);
 expect(button('Export').disabled).toBe(false);
});
it("ignores stale searches, including replies arriving during the next debounce", async () => {
  let finish!: (value: any) => void;
  vi.mocked(fetchNotionPages)
    .mockResolvedValueOnce({ pages: [] })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce({ pages: [{ id: "new", title: "Current page" }] });
  await act(async () =>
    root.render(
      <MemoryRouter>
        <NotionExport summary={summary} onClose={() => {}} />
      </MemoryRouter>,
    ),
  );
  await act(async () => {
    type("old");
    await vi.advanceTimersByTimeAsync(400);
  });
  await act(async () => type("current"));
  await act(async () =>
    finish({ pages: [{ id: "old", title: "Obsolete page" }] }),
  );
  expect(node.textContent).not.toContain("Obsolete page");
  await act(async () => vi.advanceTimersByTimeAsync(400));
  expect(node.textContent).toContain("Current page");
  expect(node.textContent).not.toContain("Obsolete page");
});
it("does not offer previous results after a failed search and can retry that query", async () => {
  vi.mocked(fetchNotionPages)
    .mockResolvedValueOnce({ pages: [{ id: "old", title: "Old notebook" }] })
    .mockRejectedValueOnce(new Error("Search connection interrupted"))
    .mockResolvedValueOnce({ pages: [{ id: "new", title: "New notebook" }] });
  await act(async () => root.render(<MemoryRouter><NotionExport summary={summary} onClose={() => {}} /></MemoryRouter>));
  expect(node.textContent).toContain("Old notebook");
  await act(async () => { type("New"); await vi.advanceTimersByTimeAsync(400); });
  expect(node.textContent).toContain("Search connection interrupted");
  expect(node.textContent).not.toContain("Old notebook");
  const submit = [...node.querySelectorAll("button")].find(button => button.textContent?.trim() === "Export")!;
  expect(submit.disabled).toBe(true);
  await act(async () => [...node.querySelectorAll("button")].find(button => button.textContent?.trim() === "Retry search")!.click());
  await act(async () => vi.advanceTimersByTimeAsync(400));
  expect(fetchNotionPages).toHaveBeenLastCalledWith("New");
  expect(node.textContent).toContain("New notebook");
  expect(node.textContent).not.toContain("Search connection interrupted");
});
it.each(["podcast", "video"])(
  "exports %s through the shared dialog with its full note",
  async (kind) => {
    vi.mocked(fetchNotionPages).mockResolvedValue({
      pages: [{ id: "target", title: "Notebook" }],
    });
    vi.mocked(exportMarkdownToNotion).mockResolvedValue({
      title: "Exported note",
      url: "https://notion.so/note",
    });
    const task = {
      id: "video",
      title: "Video note",
      platform: "youtube",
      channel: "A channel",
      duration: 90,
      url: "https://youtube.com/watch?v=abc",
    } as VideoTask;
    const props =
      kind === "podcast"
        ? { summary }
        : { task, content: "# Saved video\n\nFull video detail" };
    await act(async () =>
      root.render(
        <MemoryRouter>
          <NotionExport {...props} onClose={() => {}} />
        </MemoryRouter>,
      ),
    );
    const choose = [...node.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("Notebook"),
    )!;
    await act(async () => choose.click());
    const submit = [...node.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Export",
    )!;
    await act(async () => submit.click());
    expect(exportMarkdownToNotion).toHaveBeenCalledWith(
      expect.stringContaining(
        kind === "podcast" ? "Source detail" : "Full video detail",
      ),
      kind === "podcast" ? "Podcast note" : "Video note",
      "target",
    );
    if (kind === "video")
      expect(vi.mocked(exportMarkdownToNotion).mock.calls[0][0]).toContain(
        "Duration: 1:30",
      );
    expect(node.textContent).toContain('Exported "Exported note"');
  },
);
