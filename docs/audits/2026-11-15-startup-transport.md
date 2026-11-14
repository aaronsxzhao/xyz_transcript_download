# Startup transport recovery — 2026-11-15

Baseline: main `a6b987b0950b985c516fe8db961fe097f2d6755b`; isolated branch `codex/nov15-startup-transport`. No open PRs at intake. Follow-up to the [Nov14 handoff](https://github.com/aaronsxzhao/xyz_transcript_download/blob/b1d57d1ca2680cdb18c21977fb0a2bea4f59dc91/docs/audits/2026-11-14-handoff.md). Classic layout, import entry, statistics, appearance controls and expanded reader directory are unchanged.

## Confirmed failure and cause

Mac Chrome 157.0.8103.52, headless with Chromium sandbox, TLS verification and service workers blocked. Fresh anonymous production `/login` contexts on Nov14 16:47–16:52 UTC (Nov15 China) received HTTP200 headers but stayed in `document.readyState=loading`, with the public startup shell visible. The Email form was absent. Three default-encoding samples were >60s, 41.6s and 36.5s. Screenshots were inspected.

The critical program was the complete embedded workspace graph at the end of a roughly 692kB decoded HTML document. Its closing script and the entry import could not run until the tail arrived. No independent code path could finish startup during that stall. This is the application dependency fixed here.

A second pair of alternating gzip/default samples showed gzip incomplete after about 34s twice, while default zstd completed in 8.6s and 21.8s. Identity encoding also stalled. Compression algorithm is therefore not an established cause. A separate public-domain curl received HTTP200 but only 104,151 compressed bytes before its 30s limit. The anonymous public origin on the existing HTTP8080 route completed in 1.50s; the public hashed workspace asset through the domain completed in 5.85s (164,054 compressed bytes, cache MISS). No credentials were sent to the origin. These observations isolate slow delivery on the public document path from JavaScript execution; they do not identify a particular packet loss, ISP or Cloudflare node defect. No Cloudflare settings were changed. Free-plan analytics did not expose requested edge timing fields.

## Repair

Keep the current self-contained inline program and all page controllers. A small loader before that program can install the identical module graph from either delivery path, once. Only when the graph is still absent at the existing 12s slow-start threshold does it fetch one content-hashed public recovery asset through the existing immutable Brotli/gzip asset path. The asset uses `.js` for that established caching path but is fetched and parsed as JSON, never imported as JavaScript.

The fetch omits credentials, has a 15s abort, and has no retry loop. An inline win cancels an in-flight recovery request. A failed recovery leaves the inline program intact. A recovery win starts the same Blob/import-map module graph before document completion; the later inline copy cannot remount React or replace user state. Healthy startup has no additional request. A stalled startup may transfer an extra 161,901 Brotli bytes; it still needs one functioning delivery path. Failure before the early loader arrives remains a transport failure.

## Local verification

- Production build: 201,908 gzip bytes (197.2 KiB), below the unchanged 202,496-byte / 197.75 KiB ceiling. No budget or existing assertion was relaxed.
- Frontend: 83 files / 556 tests passed. Public frontend configuration and compressed assets: 6 pytest tests passed. The first local pytest attempt lacked dependencies; the isolated test environment was completed and the tests rerun successfully.
- `check_document_startup.py`: normal Settings/Podcasts/Summary/local-note startup still works with every external JS/CSS denied; navigation, screenshots, early data reads and watchdog diagnostics pass. With the HTML paused halfway through the unclosed embedded script, Settings became usable in 12.49s while readyState was still loading and the program tag was already present. A pause before that tag also passed in 12.44s. Credential omission, exactly one recovery request, one import map, retained mount after tail release, and inline fallback after recovery HTTP503 all passed. Before/after fixture screenshots were captured and actually inspected.
- `check_page_loading.py --baseline-dist ...`: cold/revisit loading, lazy transcript, expired/revoked sessions pass. `check_page_boundaries.py`: optional JS/CSS failure and formatting recovery pass.
- `check_series_theme_browser.py`: Chromium, Classic/Editorial × light/dark × 390/820/1440px, persisted-theme cold starts/reloads, ordinary/series mixing and pagination pass. These use controlled local data, not production service evidence.

Private raw evidence: local `appearance-checks/nov15-startup/` in the original checkout. Anonymous network measurements and synthetic screenshots only in this run so far. Authenticated artifacts must remain private.

## Release and remaining acceptance

PR/full CI, exact deployed revision and post-release Editorial acceptance are recorded by the release follow-up. Local Chromium is not CI WebKit or a physical-device claim. Normal production login requires the dedicated test credential, supplied through the local no-echo helper, not chat text; its prior temporary copy was deleted. Never count anonymous/fixture checks as authenticated production coverage.

No payment, import, model request, content reprocessing or production deletion was made. Closed Nov13/Nov14 paid validations are retained and were not repeated. Historical pending-queue event gaps and a second account/mailbox remain separate issues from this startup fix.
