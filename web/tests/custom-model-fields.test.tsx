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
function selectModel(label: string, value: string) {
  const el = node.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!;
  act(() => {
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
it.each(["summary", "transcription"] as const)("shows %s models in a dropdown and tests the selected model", async (kind) => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(Response.json({ models: ["first-model", "provider/second-model"] }))
    .mockResolvedValueOnce(Response.json({ message: "Connection verified." }));
  vi.stubGlobal("fetch", fetch);
  await act(async () => root.render(<Host kind={kind} />));
  await tick();
  const label = kind === "summary" ? "Summary" : "Transcription";
  expect(node.querySelector(`[aria-label="${label} custom model"]`)).toBeNull();
  expect(node.textContent).toContain("provider/second-model");
  selectModel(`${label} model`, "model:provider/second-model");
  await act(async () => [...node.querySelectorAll("button")].find(b => b.textContent === `Test ${kind}`)!.click());
  expect(JSON.parse(fetch.mock.calls[1][1].body)[kind === "summary" ? "llm_model" : "whisper_model"]).toBe("provider/second-model");
});
it("preserves a saved model missing from the listing and allows manual entry or returning to a listed model", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ models: ["listed-model"] })));
  await act(async () => root.render(<Host saved />));
  await tick();
  const select = node.querySelector<HTMLSelectElement>('[aria-label="Summary model"]')!;
  expect(select.selectedOptions[0].textContent).toBe("first-model · current, not in list");
  selectModel("Summary model", "manual");
  input("Summary custom model", "private/manual-model");
  expect(node.querySelector<HTMLInputElement>('[aria-label="Summary custom model"]')!.value).toBe("private/manual-model");
  selectModel("Summary model", "model:listed-model");
  expect(select.value).toBe("model:listed-model");
  expect(node.querySelector('[aria-label="Summary custom model"]')).toBeNull();
});
it("keeps manual entry visible when a pending model listing arrives", async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve; })));
  await act(async () => root.render(<Host />));
  input("Summary custom model", "private/in-progress");
  await tick();
  await act(async () => finish(Response.json({ models: ["listed-model"] })));
  expect(node.querySelector<HTMLInputElement>('[aria-label="Summary custom model"]')!.value).toBe("private/in-progress");
  expect(node.querySelector<HTMLSelectElement>('[aria-label="Summary model"]')!.value).toBe("manual");
});
it("distinguishes gateway HTML from a model rejection and allows an explicit retry", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(Response.json({models:['gpt-6.1-sol']}))
    .mockResolvedValueOnce(new Response('<!DOCTYPE html><html>private edge detail</html>', {status:502, headers:{'Content-Type':'text/html','CF-Ray':'abc123-IAD'}}))
    .mockResolvedValueOnce(Response.json({message:'Connection verified.'}));
  vi.stubGlobal('fetch', fetch);
  await act(async () => root.render(<Host/>));
  await tick();
  selectModel('Summary model','model:gpt-6.1-sol');
  const test = [...node.querySelectorAll('button')].find(b => b.textContent === 'Test summary')!;
  await act(async () => test.click());
  expect(node.textContent).toContain('website gateway');
  expect(node.textContent).toContain('abc123-IAD');
  expect(node.textContent).not.toContain('private edge detail');
  expect(node.textContent).not.toContain('DOCTYPE');
  expect(fetch).toHaveBeenCalledTimes(2);
  await act(async () => test.click());
  expect(JSON.parse(fetch.mock.calls[2][1].body).llm_model).toBe('gpt-6.1-sol');
  expect(node.textContent).toContain('Connection verified.');
  expect(fetch).toHaveBeenCalledTimes(3);
});
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
    [...node.querySelectorAll('option[value^="model:"]')].map((row) =>
      row.getAttribute("value"),
    ),
  ).toEqual(["model:second-model"]);
  await act(async () => finish(Response.json({ models: ["stale-model"] })));
  expect(node.textContent).not.toContain("stale-model");
  expect(
    node.querySelector<HTMLSelectElement>('[aria-label="Summary model"]')!
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

it("ends a stalled model-list request and permits a fresh retry without accepting late results", async () => {
  let finish!: (response: Response) => void;
  const fetch=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockResolvedValue(Response.json({models:['recovered-model']}));
  vi.stubGlobal('fetch',fetch);
  await act(async()=>root.render(<Host/>));
  await tick();
  expect(node.textContent).toContain('Reading models…');
  await act(async()=>vi.advanceTimersByTimeAsync(15000));
  expect(node.textContent).toContain('Model list request timed out');
  const refresh=[...node.querySelectorAll('button')].find(button=>button.textContent==='Refresh models')!;
  expect(refresh.disabled).toBe(false);
  await act(async()=>refresh.click());
  await tick();
  expect(node.querySelector('option[value="model:recovered-model"]')).not.toBeNull();
  await act(async()=>finish(Response.json({models:['late-model']})));
  expect(node.querySelector('option[value="model:late-model"]')).toBeNull();
  expect(node.textContent).not.toContain('timed out');
});
