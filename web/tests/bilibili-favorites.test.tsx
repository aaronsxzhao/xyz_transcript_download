// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  folders: vi.fn(),
  page: vi.fn(),
  generate: vi.fn(),
  generation: 0,
}));
vi.mock("../src/lib/bilibiliFavorites", () => ({
  fetchFavoriteFolders: mocks.folders,
  fetchFavoritePage: mocks.page,
}));
vi.mock("../src/lib/api", () => ({
  generateVideoNote: mocks.generate,
  getVideoProcessingDefaults: () => ({
    style: "tutorial",
    formats: ["link", "summary"],
  }),
}));
vi.mock("../src/lib/auth", () => ({
  getAuthGeneration: () => mocks.generation,
}));
vi.mock("../src/components/CachedImage", () => ({ default: () => null }));
import Favorites from "../src/components/video/BilibiliFavorites";

let node: HTMLDivElement, root: ReturnType<typeof createRoot>;
const imported = vi.fn();
const video = (bvid: string, extra = {}) => ({
  bvid,
  title: bvid,
  url: `https://www.bilibili.com/video/${bvid}`,
  thumbnail: "",
  duration: 60,
  uploader: "Uploader",
  available: true,
  imported: false,
  ...extra,
});
beforeEach(() => {
  vi.resetAllMocks();
  mocks.generation = 0;
  mocks.folders.mockResolvedValue({
    folders: [{ id: 10, title: "Favorites", count: 23 }],
  });
  mocks.page.mockResolvedValue({
    videos: [
      video("new"),
      video("existing", { imported: true }),
      video("unavailable", { available: false }),
    ],
    page: 1,
    has_more: true,
  });
  mocks.generate.mockResolvedValue({ task_id: "task" });
  node = document.createElement("div");
  document.body.append(node);
  root = createRoot(node);
});
afterEach(() => {
  act(() => root.unmount());
  node.remove();
});
const render = async () => {
  await act(async () =>
    root.render(
      <MemoryRouter>
        <Favorites onImported={imported} />
      </MemoryRouter>,
    ),
  );
};
const button = (text: string) =>
  Array.from(node.querySelectorAll("button")).find((row) =>
    row.textContent?.includes(text),
  )!;

it("queues only selected available videos with saved settings and duplicate protection", async () => {
  await render();
  expect(
    (node.querySelector('[aria-label="Select existing"]') as HTMLInputElement)
      .disabled,
  ).toBe(true);
  expect(
    (
      node.querySelector(
        '[aria-label="Select unavailable"]',
      ) as HTMLInputElement
    ).disabled,
  ).toBe(true);
  await act(async () => {
    (
      node.querySelector('[aria-label="Select new"]') as HTMLInputElement
    ).click();
  });
  await act(async () => button("Process selected").click());
  expect(mocks.generate).toHaveBeenCalledTimes(1);
  expect(mocks.generate).toHaveBeenCalledWith(
    expect.objectContaining({
      url: "https://www.bilibili.com/video/new",
      skip_existing: true,
      style: "tutorial",
      formats: ["link", "summary"],
    }),
  );
  expect(node.textContent).toContain("1 queued");
  expect(imported).toHaveBeenCalledOnce();
});

it("shows reconnect instructions rather than an empty favorites list", async () => {
  mocks.folders.mockRejectedValue(
    new Error("Bilibili login expired. Reconnect Bilibili in Settings."),
  );
  await render();
  expect(node.querySelector('[role="alert"]')?.textContent).toContain(
    "login expired",
  );
  expect(node.textContent).not.toContain("has no created favorite folders");
  expect(node.querySelector('a[href="/settings"]')).not.toBeNull();
  mocks.folders.mockResolvedValue({ folders: [] });
  await act(async () => button("Retry loading").click());
  expect(node.textContent).toContain("has no created favorite folders");
});

it("clears page selection and ignores a late result from the previous page", async () => {
  let finish!: (value: unknown) => void;
  mocks.page
    .mockResolvedValueOnce({
      videos: [video("first")],
      page: 1,
      has_more: true,
    })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValueOnce({
      videos: [video("third")],
      page: 3,
      has_more: false,
    });
  await render();
  await act(async () => {
    (
      node.querySelector('[aria-label="Select first"]') as HTMLInputElement
    ).click();
  });
  await act(async () => button("Next").click());
  // Changing folders aborts an older page read too.
  await act(async () => window.dispatchEvent(new Event("xyz:session-changed")));
  finish({ videos: [video("late")], page: 2, has_more: false });
  await act(async () => {});
  expect(node.textContent).not.toContain("late");
  expect(node.textContent).toContain("Process selected (0)");
});

it("stops after an ambiguous submission failure and leaves remaining choices for retry", async () => {
  mocks.page.mockResolvedValue({
    videos: [video("one"), video("two"), video("three")],
    page: 1,
    has_more: false,
  });
  mocks.generate
    .mockResolvedValueOnce({ task_id: "one" })
    .mockRejectedValueOnce(new Error("No confirmation received."));
  await render();
  await act(async () => {
    (node.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
  });
  await act(async () => button("Process selected").click());
  expect(mocks.generate).toHaveBeenCalledTimes(2);
  expect(node.querySelector('[role="alert"]')?.textContent).toContain(
    "Remaining videos were not submitted",
  );
  expect(node.textContent).toContain("1 queued");
  expect(node.textContent).toContain("Process selected (2)");
});

it("does not submit the next video after switching accounts mid-batch", async () => {
  let finish!: (value: unknown) => void;
  mocks.page.mockResolvedValue({
    videos: [video("one"), video("two")],
    page: 1,
    has_more: false,
  });
  mocks.generate.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await render();
  await act(async () => {
    (node.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
  });
  await act(async () => button("Process selected").click());
  mocks.generation++;
  mocks.folders.mockResolvedValue({ folders: [] });
  await act(async () => window.dispatchEvent(new Event("xyz:session-changed")));
  finish({ task_id: "old-owner-task" });
  await act(async () => {});
  expect(mocks.generate).toHaveBeenCalledTimes(1);
  expect(node.textContent).not.toContain("one");
  expect(imported).not.toHaveBeenCalled();
});
