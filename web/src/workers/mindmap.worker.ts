import { buildMapOutline } from "../lib/mindmapOutline";
self.onmessage = (event: MessageEvent<string>) => {
  try {
    self.postMessage({ outline: buildMapOutline(event.data) });
  } catch {
    self.postMessage({ error: "Could not prepare the mind map." });
  }
};
