// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import NotionExport from "../src/components/PodcastNotionExport";
import {
  fetchNotionPages,
  exportMarkdownToNotion,
  type Summary,
  type VideoTask,
} from "../src/lib/api";
vi.mock("../src/lib/api", () => ({
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
