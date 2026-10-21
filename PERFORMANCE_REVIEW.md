# Performance review — 20 October 2026

The previous US-runner checks did not establish acceptable performance on the
user's company network in China. Review covered the React startup/authentication
and routing graph, every page's fetch/cache/polling lifecycle, rendering and
reader dependencies, FastAPI route scheduling, database access, progress jobs,
private media delivery, and deployment/rollback.

## Pagination and reader iteration — 21 October 2026

Implemented the review's next priorities:
- `/api/library` returns 40 lightweight rows with an opaque ordering cursor.
  Cloud filtering, source search, ordering and pagination run in Postgres through
  a service-only security-invoker view. Frontend searches debounce and cancel
  superseded reads; the startup prefetch also uses the bounded endpoint. No full
  note bodies/transcripts are included. Local JSON summaries are filtered on the
  server; they do not have the cloud database's indexed query path.
- Successful writes invalidate related account cache families instead of all
  pages. Hover prefetch waits 200ms and can be cancelled before a request starts.
- Both Markdown renderers share private WebP previews (maximum 1000px dimension,
  quality 85); original images load on enlargement and remain unchanged. Missing,
  expired and network-failed images have distinct recovery actions. Preview bytes
  are cached privately and the preview-file count is bounded.
- Shared API deadlines include response bodies. An unconfirmed write explicitly
  warns it may still be running and is never automatically resubmitted on timeout.
  Video action buttons prevent duplicate clicks; processing-panel failures are
  visible and failed dismiss/retry actions retain their task.
- Readers share text size, comfortable/wide width, and contents visibility.
  Library includes server sorting, source filtering, dates and layout memory.
  Settings has a sticky save/status bar and guards unsaved navigation/closing.
  Navigation descriptions distinguish saved notes from sources and tasks.
- Account-scoped timing samples persist across cloud deployment (128 per account)
  with P50/P95 by rendering stage, including first preview completion. Settings →
  Tools & Data exposes recent account timings on demand. Local mode
  uses SQLite. Raw page URLs, content and credentials are rejected. Aggregate
  metrics are diagnostics, not promises about the user's network.

The additive migration was applied and verified: the view contained 128 distinct
account/kind/id rows at review time, unauthorized database roles cannot select the
view/table or call the append function, and a rolled-back 130-append test verified
128-sample retention. RLS is enabled on the service-only table; its no-client-policy
advisor information is intentional. Existing leaked-password-protection warning
is unrelated to this change; see https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection.

Validation covers 2,105 tied-date notes across cursor pages, filtering and owner
isolation, preview byte reduction, persistent account metrics, mutation timeouts,
request cancellation, and browser reading/settings/update/rollback interactions.
  A watcher reconciles account changes between initial render and effect setup.
CI adds Safari/WebKit and startup with optional program downloads blocked.
Historical missing source images still require source video or backup recovery.

## Workflow reliability audit — current iteration

Inspected application routing, authentication, cross-tab state, public cache and
updates, Library filtering, upload chunking/finalization, reader rendering,
background polling, settings persistence, API ownership checks, database list
queries and deployment rollback. This is a code and synthetic-flow review, not
proof that every external provider or the user's network is healthy.

Fixed in this iteration:
- Update availability appears in the header. Reload fetches a fresh document,
  retains route/query/fragment and removes the temporary recovery parameter.
  Updates do not discard an unsaved form automatically.
- Sign-in, sign-up and password recovery have connection/body deadlines; late
  login responses cannot undo logout. Cross-tab account changes invalidate
  requests and clear the previous account's UI/cache. Responses finishing body
  parsing after a session change are rejected, including stale cache fallback.
- Video upload polling stops after success or failure and cannot delay a
  successful finalization. Chunk progress counts completed bytes; failed workers
  stop scheduling further chunks. Upload response bodies have deadlines too.
- Tablet navigation includes sign-out. Library remembers grid/list preference
  and provides clear filters; failed video delete/cancel actions show errors.
- Summary polling cannot overlap or replace a newly navigated summary. Markdown
  TOC cleanup preserves ordinary prose/separators, and Unicode/entity heading
  links agree with rendered headings. Single-column topics and bounded images
  remain in place.

Remaining work and evidence limits:
- Library still loads relatively large source lists and does not implement
  server cursor pagination. PostgREST's row cap can truncate very large podcast
  collections; API pagination/search should precede further visual polish.
- Missing historical local-upload screenshots are absent from storage. CSS and
  cache changes cannot restore those files; original source or backup recovery
  is required. Existing notes/media are not rewritten by this release.
- Paid summarization and platform downloads are not re-run against users' media
  as a test. Their external availability is not established by mocked tests.
- China/company-Wi-Fi response time remains unverified. Local/CI timings are
  synthetic, and a healthy deployment does not establish that network's speed.
- Some non-upload mutation requests still lack a uniform deadline. Settings
  remains a large component; these deserve a separate, focused iteration.

Validation covers authentication races, stalled upload status/finalization,
Markdown preservation, Library preferences/filters, tablet navigation, update
and rollback behavior, reader dimensions, and the existing backend regression
suite. Release CI records the complete browser matrix and test outcomes.

## Follow-up: startup still stalled in the user's browser

### Reader layout follow-up

The optional formatting fallback exposed Markdown source, wide image previews
expanded with the viewport, and row-aligned topic cards reserved blank space
under shorter neighbours. Basic semantic Markdown now ships with startup;
syntax highlighting and math enhancements remain deferred. The complete initial
compressed document is 185.1 KiB (previously 171.5 KiB), with an explicit 190 KiB
budget and no external core JS/CSS requests. This small increase makes readable
headings, lists, links and tables independent of optional network downloads.

Both renderers share heading anchors and omit the generated duplicate TOC.
Screenshot previews fit within 760 × 420 CSS pixels, preserve aspect ratio and
native small-image size, and open full-size only on request. Readers stop
stretching at 1600px; article text is capped at 1120px. Topic cards use independent
column stacks, with original reading order retained on mobile.

Synthetic Chromium checks cover 390, 1440, 2560 and 5120px, rich and blocked-module
rendering, late landscape/portrait/small images, zoom/close, duplicate Chinese
heading navigation, expanded topic spacing and overflow. Mobile and desktop
screenshots were visually reviewed. Existing copy/export/mind-map/scroll-position
checks pass, as do 34 frontend and 249 backend tests. CI additionally exercises
WebKit. The deployment read probe now checks the reported summary and numeric
image bounds. This does not establish the user's China-network loading time.

Rollback: `safety/pre-reader-layout-20261020` / image
`1275fbc876542df16266ea212084b4db9d8a56f0`. Saved notes and media are unchanged.

A new real-user Podcasts record is 120,574ms with only 14ms spent on the
document. The telemetry's cache flag describes data, not document caching.
The supplied screenshot is the pre-framework public shell, so the
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


## Visual language iteration — 21 October 2026

Shared tokens now define text hierarchy, control sizes and surface spacing.
Desktop controls use a 36px minimum, form inputs 40px, and mobile targets 44px.
Page titles use 28/24px; reading text remains adjustable independently. Readers
keep a single content column, a comfortable default, bounded centered previews,
plain Chinese quotations and grouped exports. Existing explicit width preferences
are preserved. Settings expands to 960px; collections use responsive card grids;
mobile Library filters collapse behind a labeled control. Dashboard prioritizes
active work and recent reading before adding content and statistics.

UI labels remain consistently English; note content is never translated or edited.
No fonts, animation libraries or new runtime dependencies were added.

Retained technical backlog from the preceding review (outside this visual release):
- Server pagination for video channels, not only Library.
- Persist pre-generated image previews instead of converting on the first read.
- Preserve Library results while a new search is pending.
- Bounded asynchronous caching for large notes and filter combinations.
- Visit-correlated timing samples split by cold/warm and ready/error outcomes.
- Explicit platform-account fetch failure states.
- Topic-level podcast navigation and continuous image browsing/zoom.

Rollback: safety/pre-visual-language-20261021 (af4de4b).
