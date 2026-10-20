# Performance review — 20 October 2026

The previous US-runner checks did not establish acceptable performance on the
user's company network in China. Review covered the React startup/authentication
and routing graph, every page's fetch/cache/polling lifecycle, rendering and
reader dependencies, FastAPI route scheduling, database access, progress jobs,
private media delivery, and deployment/rollback.

## Follow-up: startup still stalled in the user's browser

A new real-user Podcasts record is 120,574ms with only 14ms spent on the cached
document. The supplied screenshot is the pre-framework public shell, so the
previous route-boundary checks covered the wrong failure boundary. US-runner
success does not establish the user's actual startup performance.

The initial static module graph now travels inside the public document. The
browser creates document-local module URLs and an import map so optional
formatters reuse the same runtime; no initial JS/CSS downloads are required.
Only public program text is embedded. User data still uses authenticated APIs.
The public shell and early reads precede the program to retain streaming paint.
The complete compressed document/assets fit the existing 175 KiB limit.

Cold checks deny every external JS/CSS request: all four baseline pages fail;
the replacement opens Settings, Podcasts, a summary and a completed local note,
with interactive navigation and fallback screenshots. A three-second streamed
program pause leaves navigation visible and starts the settings read before the
program arrives. The watchdog is checked with no framework executing at all.
Startup telemetry distinguishes bootstrap from application measurements using
fixed labels and numeric counters; it rejects URLs and remains account scoped.

These controlled checks prove removal of the startup asset dependency; they do
not measure China's physical connection latency. Historical local screenshots
missing from Storage remain a separate data-recovery limitation.

## Follow-up: completed pages fail to open

The reported podcast and video notes exist, and both completed local videos have
saved Markdown. The three failing controllers were still separate route files.
Denying optional JavaScript requests reproduces all four failures on the previous
build. The replacement keeps every controller in the main workspace and defers
only formatting/virtualization, with readable text and screenshot fallbacks.
WebKit also retains failed module URLs across reloads: explicit recovery installs a public import map before module evaluation to refresh the entire module graph, while normal visits keep stable URLs. Inline app CSS also removes the stylesheet readiness gate. Cold startup includes
167.4 KiB compressed program/styles (175 KiB limit); this deliberate increase
eliminates additional controller requests. Public-cache privacy rules remain.

Regression coverage denies every additional optional JS file while navigating
to Settings, the reported podcast/video, and a completed local video; checks
fallback screenshots and recovery; and separately denies stylesheet requests.
This is controlled failure testing, not a claim about the user's China latency.
Live diagnostics also cover the newly reported summary and an owned completed
local video. No stored note bodies, uploads, or schema are modified.

## Evidence and repairs

| Finding | Evidence | Repair |
| --- | --- | --- |
| First documents and route files can dominate the wait | Real user timing records: dashboard document 12,702ms; Videos worst 77,609ms; channel worst 49,504ms. US live API checks commonly 50–200ms. | Consolidate ordinary workspace modules, keep heavy readers deferred, and cache public shell/program files for repeat document visits. |
| Some asynchronous actions execute blocking database calls | Video retry, channel scan, cookie validation/save, and Notion export called synchronous database methods on the event loop. | Run those calls in worker threads. Concurrent health/settings tests hold each action's database operation open and verify other reads still respond. |
| Progress reads unnecessarily include the entire video inventory | Existing queue response was 135,700 decoded bytes / 23,025 gzip bytes on the production profile. | Separate progress queries for active tasks, ten recent completions and explicitly known tasks; project only progress metadata, preserve pending writes, enforce ownership on every query. |
| Browsing triggers unrelated work | Automatic list-arrival prefetch loads two readers/notes; channel polling duplicates global progress reconciliation. | Keep intent-based prefetch, remove speculative list-arrival fetches, and use global progress reconciliation. |
| A statistics read can remain pending | Dashboard used unbounded direct fetch. | Use the shared bounded, deduplicated JSON reader. |

## Validation

- 249 backend tests and 32 frontend tests pass.
- Controlled network test (one second per asset): Settings usable 2,522→1,326ms;
  initial program requests 11→6; Library navigation 1,367→146ms with no new
  program requests. These are synthetic comparisons, not China timings.
- After caching, a repeat document/form takes 208ms despite an injected
  twelve-second origin document delay. Offline checks prove APIs and private
  screenshots remain network-only. Upgrade and rollback both remain usable,
  with at most two public-file cache generations.
- Reader checks cover 390/768/1440/1920px, summaries, images, mindmaps, copy,
  exports, reading-position retention and source failures. Session expiry,
  revocation, slow reads and replaced-entry recovery remain covered.

## Limits and rollback

An entirely new browser must still reach the public domain before local public
files exist. This patch cannot guarantee the first connection's latency in
China; persistent cold-connection delay requires measuring and changing the
delivery/hosting route. No database migration, note rewrite, provider change or
media deletion is part of this repair. The preceding source and deployment image
are retained; see ROLLBACK.md. Production verification records actual cold page
checks and a separate public-cache reload check.
