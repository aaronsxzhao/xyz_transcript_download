# Startup transport recovery — 2026-11-15

Baseline: main `a6b987b0950b985c516fe8db961fe097f2d6755b`; isolated branch `codex/nov15-startup-transport`. No open PRs at intake. Follow-up to the [Nov14 handoff](https://github.com/aaronsxzhao/xyz_transcript_download/blob/b1d57d1ca2680cdb18c21977fb0a2bea4f59dc91/docs/audits/2026-11-14-handoff.md). Classic layout, import entry, statistics, appearance controls and expanded reader directory are unchanged.

## Confirmed failure and cause

Mac Chrome 157.0.8103.52, headless with Chromium sandbox, TLS verification and service workers blocked. Fresh anonymous production `/login` contexts on Nov14 16:47–16:52 UTC (Nov15 China) received HTTP200 headers but stayed in `document.readyState=loading`, with the public startup shell visible. The Email form was absent. Three default-encoding samples were >60s, 41.6s and 36.5s. Screenshots were inspected.

The critical program was the complete embedded workspace graph at the end of a roughly 692kB decoded HTML document. Its closing script and the entry import could not run until the tail arrived. No independent code path could finish startup during that stall. This is the application dependency fixed here.

A second pair of alternating gzip/default samples showed gzip incomplete after about 34s twice, while default zstd completed in 8.6s and 21.8s. Identity encoding also stalled. Compression algorithm is therefore not an established cause. A separate public-domain curl received HTTP200 but only 104,151 compressed bytes before its 30s limit. The anonymous public origin on the existing HTTP8080 route completed in 1.50s; the public hashed workspace asset through the domain completed in 5.85s (164,054 compressed bytes, cache MISS). No credentials were sent to the origin. These observations isolate slow delivery on the public document path from JavaScript execution; they do not identify a particular packet loss, ISP or Cloudflare node defect. No Cloudflare settings were changed. Free-plan analytics did not expose requested edge timing fields.

A separate 390px Editorial production check reproduced both states: light stayed on the shell beyond 30s; dark initially opened in 13.03s, but its reload took 25.41s and displayed Classic. The latter screenshot was inspected. The selected skin was requested only after the whole program arrived, so its unchanged 8s cosmetic timeout could discard Editorial on a slow transfer. Request routing disables the browser HTTP cache in these checks; this is a strict cold-network reload, not a normal warm-cache estimate.

## Repair

Keep the current self-contained inline program and all page controllers. A small loader before that program can install the identical module graph from either delivery path, once. Only when the graph is still absent at the existing 12s slow-start threshold does it fetch one content-hashed public recovery asset through the existing immutable Brotli/gzip asset path. The asset uses `.js` for that established caching path but is fetched and parsed as JSON, never imported as JavaScript.

The fetch omits credentials, has a 15s abort, and has no retry loop. An inline win cancels an in-flight recovery request. A failed recovery leaves the inline program intact. A recovery win starts the same Blob/import-map module graph before document completion; the later inline copy cannot remount React or replace user state. Healthy startup has no additional program request. A stalled startup may transfer an extra 161,901 Brotli bytes; it still needs one functioning delivery path. Failure before the early loader arrives remains a transport failure.

The pre-paint theme bootstrap also preloads only the persisted Editorial or Classic-light stylesheet as `preload as=style`, with matching anonymous CORS mode. It does not apply the skin early or change CSS order. The existing appearance import attaches the actual stylesheet and retains its original 8s timeout. This overlaps the skin transfer with the HTML instead of serializing it after startup.

## Local verification

- Production build: 202,067 gzip bytes (197.3 KiB), below the unchanged 202,496-byte / 197.75 KiB ceiling. No budget or existing assertion was relaxed.
- Frontend: 83 files / 556 tests passed. Public frontend configuration and compressed assets: 6 pytest tests passed. The first local pytest attempt lacked dependencies; the isolated test environment was completed and the tests rerun successfully.
- `check_document_startup.py`: normal Settings/Podcasts/Summary/local-note startup still works with every external JS/CSS denied; navigation, screenshots, early data reads and watchdog diagnostics pass. With the HTML paused halfway through the unclosed embedded script, Settings became usable in 12.49s while readyState was still loading and the program tag was already present. A pause before that tag also passed in 12.44s. Credential omission, exactly one recovery request, one import map, retained mount after tail release, inline fallback after recovery HTTP503, and cancellation of an already-started recovery transfer when inline wins all passed. Before/after fixture screenshots were captured and actually inspected.
- Selected-skin counterexample: same 3s streamed document and 9s skin transfer. Baseline requested the skin after the program and fell back to Classic in 11.25s. Candidate requested it before the program, retained Editorial light and became usable in 9.21s. The 8s style timeout was not changed. Candidate screenshot was actually inspected. The 12 Chromium persisted-theme series cases were repeated after this change and all passed.
- `check_first_paint.py`: navigation 86ms, Settings usable 2.07s with delayed fixture APIs; original timing and no-entry-request assertions pass. `check_network_resilience.py`: offline public shell, saved settings, update notification, route-preserving reload and rollback pass.
- `check_page_loading.py --baseline-dist ...`: cold/revisit loading, lazy transcript, expired/revoked sessions pass. `check_page_boundaries.py`: optional JS/CSS failure and formatting recovery pass.
- `check_series_theme_browser.py`: Chromium, Classic/Editorial × light/dark × 390/820/1440px, persisted-theme cold starts/reloads, ordinary/series mixing and pagination pass. These use controlled local data, not production service evidence.

Private raw evidence: local `appearance-checks/nov15-startup/` in the original checkout. Anonymous network measurements and synthetic screenshots only in this run so far. Authenticated artifacts must remain private.

## Release and remaining acceptance

The first PR CI failed because `check_first_paint.py` still parsed only a module-script entry tag. Its parser now recognizes the early loader data-entry attribute as well; all original behavior/timing assertions remain. The full corresponding first-paint/network lane was rerun locally and passed.

PR/full CI, exact deployed revision and post-release Editorial acceptance are recorded by the release follow-up. Local Chromium is not CI WebKit or a physical-device claim. Normal production login requires the dedicated test credential, supplied through the local no-echo helper, not chat text; its prior temporary copy was deleted. Never count anonymous/fixture checks as authenticated production coverage.

No payment, import, model request, content reprocessing or production deletion was made. Closed Nov13/Nov14 paid validations are retained and were not repeated. Historical pending-queue event gaps and a second account/mailbox remain separate issues from this startup fix.
