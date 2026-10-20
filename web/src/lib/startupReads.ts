type EarlyRead = { token: string; response: Promise<{body: string; status: number; headers: Headers} | null> }
declare global { interface Window { __xyzStartupReads?: Map<string, EarlyRead> } }

/** Only the identical session can consume a read started by this document. */
export function takeStartupRead(url: string, token: string | null): Promise<Response | null> | null {
  if (!token || !window.__xyzStartupReads) return null
  const key = new URL(url, location.origin); if (key.origin !== location.origin) return null; key.searchParams.sort()
  const name = key.pathname + key.search
  const entry = window.__xyzStartupReads.get(name)
  if (!entry) return null
  window.__xyzStartupReads.delete(name)
  if (entry.token !== token) return null
  return entry.response.then(result => result ? new Response(result.body, {status:result.status, headers:result.headers}) : null)
}
