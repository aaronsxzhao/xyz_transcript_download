// @vitest-environment jsdom
import React, { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import CustomModelFields from "../src/components/CustomModelFields";
import { clearTokens } from "../src/lib/auth";

let node: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  clearTokens();
  localStorage.clear();
  vi.useFakeTimers();
  node = document.createElement("div");
  document.body.append(node);
  root = createRoot(node);
});
afterEach(() => {
  act(() => root.unmount());
  node.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
function Host({
  saved = false,
  kind = "summary",
}: {
  saved?: boolean;
  kind?: "summary" | "transcription";
}) {
  const [value, setValue] = useState<{ baseUrl: string; apiKey?: string }>({
    baseUrl: "https://first.example/v1",
    apiKey: saved ? undefined : "private-key",
  });
  const [model, setModel] = useState("first-model");
  return (
    <CustomModelFields
      kind={kind}
      value={value}
      model={model}
      keySaved={saved}
      savedBase="https://first.example/v1"
      onChange={setValue}
      onModel={setModel}
    />
  );
}
function input(label: string, value: string) {
  const el = node.querySelector<HTMLInputElement>(`[aria-label="${label}"]`)!;
  act(() => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function tick() {
  await act(async () => vi.advanceTimersByTimeAsync(650));
}
it("replaces the endpoint model list and ignores an older response", async () => {
  let finish!: (response: Response) => void;
  const fetch = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue(Response.json({ models: ["second-model"] }));
  vi.stubGlobal("fetch", fetch);
  await act(async () => root.render(<Host />));
  await tick();
  input("Summary Base URL", "https://second.example/v1");
  await tick();
  expect(
    [...node.querySelectorAll("datalist option")].map((row) =>
      row.getAttribute("value"),
    ),
  ).toEqual(["second-model"]);
  await act(async () => finish(Response.json({ models: ["stale-model"] })));
  expect(node.textContent).not.toContain("stale-model");
  expect(
    node.querySelector<HTMLInputElement>('[aria-label="Summary custom model"]')!
      .value,
  ).toBe("");
  expect(JSON.parse(fetch.mock.calls[1][1].body).llm_base_url).toBe(
    "https://second.example/v1",
  );
});
it("does not send a saved key to a changed endpoint and keeps credentials out of browser storage", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(Response.json({ models: ["first-model"] }));
  vi.stubGlobal("fetch", fetch);
  await act(async () => root.render(<Host saved />));
  await tick();
  expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty(
    "llm_api_key",
  );
  input("Summary Base URL", "https://second.example/v1");
  await tick();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(node.textContent).toContain("Re-enter the key");
  input("Summary API key", "replacement-secret");
  await tick();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(JSON.stringify(localStorage)).not.toContain("replacement-secret");
});
it("explains a model listing failure, allows manual selection and tests the audio API separately", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(
        { detail: "No /models API. Enter its documented model ID manually." },
        { status: 404 },
      ),
    )
    .mockResolvedValueOnce(Response.json({ message: "Connection verified." }));
  vi.stubGlobal("fetch", fetch);
  await act(async () => root.render(<Host kind="transcription" />));
  await tick();
  expect(node.textContent).toContain("manually");
  input("Transcription custom model", "speech-model");
  await act(async () =>
    [...node.querySelectorAll("button")]
      .find((b) => b.textContent === "Test transcription")!
      .click(),
  );
  expect(fetch.mock.calls[1][0]).toBe("/api/settings/test-transcription");
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({
    whisper_model: "speech-model",
    whisper_api_key: "private-key",
  });
  expect(node.textContent).toContain("Save Settings");
  expect(
    fetch.mock.calls.every(
      (call) => !String(call[0]).endsWith("/api/settings"),
    ),
  ).toBe(true);
});
