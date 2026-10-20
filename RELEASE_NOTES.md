# Document-contained startup — 20 October 2026

- The user's browser recorded a Podcasts visit of 120,574ms despite a 14ms cached document. Successful US-runner visits had hidden this startup failure.
- Deliver the initial program with the public document instead of waiting for three separate module requests. Preserve a single module identity so optional rich formatting shares the same React runtime.
- Put navigation and early authenticated reads before the embedded program, so streaming HTML can paint and fetch data before all program bytes arrive. Optional formatters and mindmaps retain hashed public URLs and readable fallbacks.
- Report pre-framework slow/error startup with fixed page labels and bounded numeric counters. No URLs, content, error text or credentials are retained. Manual startup retry bypasses an older cached shell.
- Test first-ever visits with all external JS/CSS denied, a streamed document, interactive navigation, optional module recovery, public-cache privacy, upgrade and rollback. Include Chromium and WebKit.
- Initial compressed document and assets remain within the existing 175 KiB limit (about 171.5 KiB); the measurement now includes all inline code and markup. No notes, uploads, account settings or schema are changed.

Rollback: `safety/pre-document-startup-20261020`, image `2bee12fc16f122b536fc56adf36c45ee054b3a84`.

---

# Completed uploads, readers and Settings repair — 20 October 2026

- Settings, podcast readers and video readers now share the initial workspace program. A failed optional file cannot prevent their controls and data reads from opening.
- Rich formatting and transcript virtualization load separately. Until available, saved text and video screenshots remain readable; a formatting failure offers a fresh-document retry that bypasses an older cached shell. Recovery uses fresh URLs for the public module graph because WebKit can retain failed import URLs across reloads.
- Inline the application stylesheet in the public HTML and mount React immediately, removing the stylesheet-event wait that could strand startup.
- Add Chromium and WebKit checks for blocked optional program files and separate stylesheets, including completed local videos, screenshot fallback and formatting recovery.
- Keep saved notes, uploads, settings, account authorization and database schema intact. The compressed initial program/style budget is now 175 KiB (167.4 KiB measured), covering every page controller; large formatting libraries remain optional.

Rollback: `safety/pre-page-repair-20261020`, image `10ed582f084d2633e7b43e4008f3398c742f33c8`. See [ROLLBACK.md](ROLLBACK.md).

---

# Network and request responsiveness repair — 20 October 2026

- Real browser records included a 12.7s document load, a 77.6s Videos visit and a
  49.5s channel visit, while most server queries took tens to hundreds of ms.
- Consolidate common workspace code so ordinary list navigation needs no new
  program files. Keep large reader/formatter dependencies deferred.
- Cache only public program files and the generic public shell for repeat hard
  visits; retain background revalidation, update notification and rollback.
- Replace background whole-library reads with bounded, account-scoped progress
  snapshots, including known jobs that completed between polls.
- Remove automatic reader downloads on list arrival and redundant channel polls.
- Move remaining blocking database work in retry, channel scan, cookie validation
  and Notion export off the event loop. Bound dashboard statistics reads.
- Add slow-network, offline public-cache, update and rollback browser checks.

---

# First paint and startup repair — 20 October 2026

- Public navigation and a page frame are included in HTML and styled inline, so slow framework/style downloads do not leave an empty screen. Authentication waits also retain navigation; private content still requires server authorization.
- Valid-session page reads start while the framework downloads and are consumed once by the matching session. Expired sessions use the normal refresh flow; config/session/refresh requests now have bounded body-read deadlines.
- Public JavaScript and CSS are precompressed as Brotli and gzip. Variant ETags, cache headers and Range handling remain separate from private API responses.
- A missing entry script triggers one bounded fresh-document retry, preserving the URL query and fragment. Persistent failures leave navigation and a manual retry, rather than a reload loop.

Checkpoint: `safety/pre-startup-repair-20261020`, image `d3fe060e8e7046a3a359b7f57765f8a38f92a49d`. No saved notes or schema changed.

---

# Reader and Library repair — 20 October 2026

- Library fills the available width with responsive cards or a list, shows the first returning source immediately, and keeps readable notes when another source fails. Large results load 60 at a time.
- The video reader uses the available content width, shows labeled export buttons, reserves screenshot space, and preserves notes and their scroll position across view changes. Podcast summary fields render Markdown and topic cards fill two columns on wide screens.
- Mind Map uses a smaller local-only transformer, a defined canvas height, proper zoom APIs, loading/retry states, resize handling and instance cleanup. Screenshots are excluded from the map to avoid duplicate image downloads; they remain in the note.
- Generated image links stay stable within a day. A private 256 MiB, 24-hour read-through cache shares concurrent downloads; valid file signatures remain required even for cache hits. The first two note screenshots load eagerly.
- PDF preparation stays pending until the print document and its images load; preparation failures are visible and temporary documents are cleaned up. Empty Library results wait for both sources before showing an empty state.
- Copy displays progress and supports Safari's clipboard activation rules. Backup and repair actions are grouped under a disclosure.

Rollback: `safety/pre-reader-repair-20261020`; deployed image `aca4f9bb29b90cb08b1fef6a97ab4f8efdd3d7e9`. No saved note bodies or database schema are changed. Earlier rollback checkpoints remain available. See [ROLLBACK.md](ROLLBACK.md).

---

# Reliability and usability release — 20 October 2026

The old release is preserved. See [ROLLBACK.md](ROLLBACK.md) for the exact source tag, built image, private backups and the GitHub rollback workflow. Rollback does not erase newer notes or images.

## Changes

- Final video notes and version history commit together. Failed saves retain private recovery copies; the reader can recover them without another model call.
- Podcast job history survives container replacement. Interrupted jobs become retryable and retain their original source, model choice and regeneration intent; video retries retain saved transcripts. Podcast source lookups, maintenance reads and cloud history writes run outside the event loop. Deletion prevents late checkpoints from restoring removed history.
- Screenshot failures have visible warnings and separate repair controls. New notes retain missing-image references so future repairs work without changing note text. Original local videos can be uploaded again for screenshot recovery.
- Per-note ZIP downloads include Markdown and available images. Settings → Tools & Data provides an account backup and an integrity check across current notes and versions. Exports exclude credentials/authentication sessions. Keep original media files separately.
- The Library combines saved podcast/video notes with title/source search and type, source and status filters. Recent notes precede statistics on the dashboard.
- Mobile forms expose the Generate button sooner, with quality controls under Advanced. Cloud platform connection instructions reflect supported methods; saved credentials are not presented as verified sessions.
- Both readers have font-size controls, mobile contents navigation and reading-position retention. Dialogs support Escape/focus trapping; images are keyboard accessible. Secondary text contrast and accessible control names are improved.
- Login supports password recovery. New passwords receive an anonymous five-character hash-prefix breach check. Supabase's separate native leaked-password setting still requires its dashboard control; the app's check does not change that setting.
- Public account-neutral HTML uses ETag validation, hashed assets remain immutable, and the Library receives route preloads and bounded API reads. Private API responses and account caches remain isolated.
- Updated frontend packages and lockfile; npm audit reports zero known advisories. Removed tracked node_modules. Node 22 builds the frontend/runtime tools.
- Added two foreign-key indexes, optimized ownership policies, and kept job/credential/backup tables inaccessible to browser roles. Database changes remain compatible with the preserved release.

## Validation and limits

Local checks: 233 backend tests, 25 frontend tests, production build and dependency audit. Live database transaction checks verified atomic saving, idempotent retry, conflict preservation and unrelated-account isolation. The expanded browser review checked 54 states at 320, 390, 768 and 1280 pixels with no detected WCAG A/AA violations, horizontal overflow or browser errors. Browser regression scripts cover large transcripts, note versions, slow reads and revoked sessions. Synthetic network timings are not a guarantee for connections from China; origin and database remain in the US.

The recovery workflow restored 238 additional historical frames, with zero note-content changes. Some original sources remain unavailable or require the original local video. Tools & Data reports remaining missing frames instead of silently claiming complete recovery. Private backup restoration was verified by downloading/reconstructing the ZIP and checking every entry. Deployment verifies that the preserved rollback image exists and restores it automatically if release health verification fails.

Job restart reconciliation currently assumes the deployed single application process. Additional replicas require job leases before scaling.
