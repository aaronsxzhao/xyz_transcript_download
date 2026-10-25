import { useEffect, useRef, useState } from "react";
import { authFetch, parseApiResponseAsJson } from "../lib/api";

export type ConnectionDraft = { baseUrl: string; apiKey?: string };
export default function CustomModelFields({
  kind,
  value,
  model,
  keySaved,
  savedBase,
  keyError = "",
  checkingSaved = false,
  onChange,
  onModel,
  disabled = false,
}: {
  kind: "summary" | "transcription";
  value: ConnectionDraft;
  model: string;
  keySaved: boolean;
  savedBase: string;
  keyError?: string;
  checkingSaved?: boolean;
  onChange: (value: ConnectionDraft) => void;
  onModel: (model: string) => void;
  disabled?: boolean;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [listingError, setListingError] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [manualEntry, setManualEntry] = useState(false);
  const version = useRef(0);
  const prefix = kind === "summary" ? "llm" : "whisper";
  const payload = () => ({
    kind,
    [prefix + "_base_url"]: value.baseUrl,
    [prefix + "_api_key"]: value.apiKey,
    [prefix + "_model"]: model,
    ...(kind === "summary"
      ? { llm_provider: "custom" }
      : { transcription_provider: "custom" }),
  });
  const canUseKey =
    !!value.apiKey ||
    (value.apiKey === undefined &&
      keySaved &&
      value.baseUrl.replace(/\/$/, "") === savedBase.replace(/\/$/, ""));
  useEffect(() => setManualEntry(false), [value.baseUrl, kind]);
  useEffect(() => {
    version.current++;
    setModels([]);
    setListingError("");
    setResult("");
    setLoading(false);
    setTesting(false);
    if (!value.baseUrl || !canUseKey) return;
    const controller = new AbortController();
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      setLoading(true);
      deadline = setTimeout(() => {
        setListingError("Model list request timed out. Retry, or enter a model ID manually.");
        setLoading(false);
        controller.abort();
      }, 15000);
      void authFetch("/api/settings/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
        signal: controller.signal,
      })
        .then((r) =>
          parseApiResponseAsJson<{ models: string[] }>(
            r,
            "Cannot read provider models",
          ),
        )
        .then((data) => {
          if (!controller.signal.aborted) {
            setModels(data.models);
            if (!data.models.length)
              setListingError(
                "The provider returned no models. Enter its documented model ID manually.",
              );
          }
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setListingError(
              error instanceof Error
                ? error.message
                : "Cannot read models. Enter a model ID manually.",
            );
        })
        .finally(() => {
          clearTimeout(deadline);
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 600);
    return () => {
      clearTimeout(timer);
      clearTimeout(deadline);
      controller.abort();
      version.current++;
    };
  }, [value.baseUrl, value.apiKey, keySaved, savedBase, refresh, kind]);
  useEffect(() => {
    setResult("");
    setTesting(false);
    version.current++;
  }, [model]);
  async function test() {
    const attempt = ++version.current;
    setTesting(true);
    setResult("");
    try {
      const response = await authFetch(
        kind === "summary"
          ? "/api/settings/test-llm"
          : "/api/settings/test-transcription",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload()),
        },
      );
      const data = await parseApiResponseAsJson<{ message: string }>(
        response,
        "Connection test failed",
      );
      if (attempt === version.current)
        setResult(data.message + " Save Settings to use this configuration.");
    } catch (error) {
      if (attempt === version.current)
        setResult(
          error instanceof Error ? error.message : "Connection test failed",
        );
    } finally {
      if (attempt === version.current) setTesting(false);
    }
  }
  const label = kind === "summary" ? "Summary" : "Transcription";
  return (
    <div className="space-y-3 rounded-lg border border-dark-border p-3">
      <p className="text-xs text-gray-400">
        OpenAI-compatible API.{" "}
        {kind === "summary"
          ? "Requires chat completions with JSON output."
          : "Requires /audio/transcriptions with verbose JSON and segment timestamps; chat models alone cannot transcribe audio."}{" "}
        Your key is encrypted on the server and is never returned here.
      </p>
      <label className="block text-sm">
        {label} Base URL
        <input
          type="url"
          aria-label={`${label} Base URL`}
          value={value.baseUrl}
          disabled={disabled}
          onChange={(e) => {
            onChange({ ...value, baseUrl: e.target.value });
            onModel("");
          }}
          placeholder="https://api.example.com/v1"
          className="mt-1 block w-full rounded-lg bg-dark-hover border border-dark-border px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        {label} API key
        <input
          type="password"
          aria-label={`${label} API key`}
          autoComplete="new-password"
          value={value.apiKey || ""}
          disabled={disabled}
          placeholder={
            keySaved && value.apiKey === undefined
              ? "Key saved · leave blank to keep"
              : "Enter provider API key"
          }
          onChange={(e) => onChange({ ...value, apiKey: e.target.value || undefined })}
          className="mt-1 block w-full rounded-lg bg-dark-hover border border-dark-border px-3 py-2"
        />
      </label>
      <p role="status" className="text-xs text-gray-400 break-words">
        {value.apiKey
          ? "New API key entered. Click Save Settings to store it; testing alone does not save it."
          : checkingSaved
            ? "Checking saved API key status…"
            : keyError
              ? "Saved API key needs attention. It could not be read; see the error below."
              : keySaved
                ? canUseKey
                  ? "API key saved on server. Hidden here; leave empty to keep it."
                  : "An API key is saved for the previous Base URL."
                : "No API key saved for this service."}
      </p>
      {keySaved &&
        value.apiKey === undefined &&
        !canUseKey && (
          <p role="status" className="text-sm text-amber-300">
            Base URL changed. Re-enter the key for this endpoint.
          </p>
        )}
      <label className="block text-sm">
        {label} model
        <select
          aria-label={`${label} model`}
          value={manualEntry ? "manual" : model ? `model:${model}` : ""}
          disabled={disabled}
          onChange={(e) => {
            const manual = e.target.value === "manual";
            setManualEntry(manual);
            if (!manual) onModel(e.target.value.slice("model:".length));
          }}
          className="mt-1 block w-full min-w-0 rounded-lg bg-dark-hover border border-dark-border px-3 py-2 text-ellipsis"
        >
          <option value="" disabled>
            {loading ? "Reading models…" : models.length ? "Choose a model" : "No models loaded · enter manually"}
          </option>
          {model && !models.includes(model) && (
            <option value={`model:${model}`}>{model} · current, not in list</option>
          )}
          {models.map((id) => (
            <option key={id} value={`model:${id}`}>{id}</option>
          ))}
          <option value="manual">Enter model ID manually…</option>
        </select>
      </label>
      {(manualEntry || (!loading && !models.length)) && (
        <label className="block text-sm">
          Model ID
          <input
            aria-label={`${label} custom model`}
            value={model}
            disabled={disabled}
            onChange={(e) => {
              setManualEntry(true);
              onModel(e.target.value);
            }}
            placeholder="Enter the provider's exact model ID"
            className="mt-1 block w-full min-w-0 rounded-lg bg-dark-hover border border-dark-border px-3 py-2"
          />
        </label>
      )}
      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          disabled={disabled || loading || !canUseKey || !value.baseUrl}
          onClick={() => setRefresh((n) => n + 1)}
          className="border border-dark-border rounded-lg px-3 py-2 text-sm"
        >
          {loading ? "Reading models…" : "Refresh models"}
        </button>
        <span role="status" className="text-xs text-gray-400">
          {models.length > 0
            ? `${models.length} models from this endpoint`
            : ""}
        </span>
        <button
          type="button"
          disabled={
            disabled || testing || !canUseKey || !value.baseUrl || !model
          }
          onClick={() => void test()}
          className="border border-dark-border rounded-lg px-3 py-2 text-sm"
        >
          {testing ? "Testing…" : `Test ${kind}`}
        </button>
      </div>
      {listingError && (
        <p role="status" className="text-sm text-amber-300 break-words">
          {listingError}
        </p>
      )}
      {result && (
        <p role="status" className="text-sm break-words">
          {result}
        </p>
      )}
      <p className="text-xs text-gray-400">
        Model lists may include unsupported models. Tests use synthetic input
        and may incur a small provider charge. A successful connection does not
        guarantee a model's full-length capacity.
      </p>
    </div>
  );
}
