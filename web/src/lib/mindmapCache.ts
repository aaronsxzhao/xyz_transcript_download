import { getCache, hydrateCache, setCache } from "./cache";
import { getAccountId } from "./preferences";
import { MAP_FORMAT, type MapOutline } from "./mindmapOutline";

export async function mapCacheKey(markdown: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(markdown),
  );
  return (
    // Hash the actual worker input. Image-like text inside code is meaningful;
    // regex stripping could alias different notes. Isolate older stripped keys.
    `mindmap:v${MAP_FORMAT}:source:` +
    Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("")
  );
}
export async function prepareMindMap(
  markdown: string,
  signal: AbortSignal,
): Promise<MapOutline> {
  const owner = getAccountId();
  const key = await mapCacheKey(markdown);
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  await hydrateCache(key);
  if (signal.aborted || owner !== getAccountId())
    throw new DOMException("Cancelled", "AbortError");
  const cached = getCache<MapOutline>(key);
  if (cached) return structuredClone(cached); // Markmap mutates its tree; keep the cached outline pristine.
  const outline = await new Promise<MapOutline>((resolve, reject) => {
    const worker = new Worker(
      new URL("../workers/mindmap.worker.ts", import.meta.url),
      { type: "module" },
    );
    const finish = (value?: MapOutline, error?: Error) => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      worker.terminate();
      if (error) reject(error);
      else resolve(value!);
    };
    const abort = () =>
      finish(undefined, new DOMException("Cancelled", "AbortError"));
    const timer = setTimeout(
      () =>
        finish(
          undefined,
          new Error("Mind map preparation timed out. Please retry."),
        ),
      15000,
    );
    signal.addEventListener("abort", abort, { once: true });
    worker.onmessage = (event) => {
      if (event.data.outline) finish(event.data.outline);
      else
        finish(
          undefined,
          new Error(event.data.error || "Could not prepare the mind map."),
        );
    };
    worker.onerror = () =>
      finish(
        undefined,
        new Error("Could not load mind map tools. Please retry."),
      );
    worker.postMessage(markdown);
  });
  if (signal.aborted || owner !== getAccountId())
    throw new DOMException("Cancelled", "AbortError");
  setCache(key, outline, owner);
  return structuredClone(outline);
}
