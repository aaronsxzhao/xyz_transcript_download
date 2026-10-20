# Reliability and usability release — 20 October 2026

The old release is preserved. See [ROLLBACK.md](ROLLBACK.md) for the exact source tag, built image, private backups and the GitHub rollback workflow. Rollback does not erase newer notes or images.

## Changes

- Final video notes and version history commit together. Failed saves retain private recovery copies; the reader can recover them without another model call.
- Podcast job history survives container replacement. Interrupted jobs become retryable and retain their original source; video retries retain saved transcripts. Cloud history writes run outside the event loop and job-status lock.
- Screenshot failures have visible warnings and separate repair controls. New notes retain missing-image references so future repairs work without changing note text. Original local videos can be uploaded again for screenshot recovery.
- Per-note ZIP downloads include Markdown and available images. Settings → Tools & Data provides an account backup and an integrity check across current notes and versions. Exports exclude credentials/authentication sessions. Keep original media files separately.
- The Library combines saved podcast/video notes with title/source search and type, source and status filters. Recent notes precede statistics on the dashboard.
- Mobile forms expose the Generate button sooner, with quality controls under Advanced. Cloud platform connection instructions reflect supported methods; saved credentials are not presented as verified sessions.
- Both readers have font-size controls, mobile contents navigation and reading-position retention. Dialogs support Escape/focus trapping; images are keyboard accessible. Secondary text contrast and accessible control names are improved.
- Login supports password recovery. New passwords receive an anonymous five-character hash-prefix breach check. Supabase's separate native leaked-password setting still requires its dashboard control; the app's check does not change that setting.
- Public account-neutral HTML has short caching and ETags, hashed assets remain immutable, and the Library receives route preloads and bounded API reads. Private API responses and account caches remain isolated.
- Updated frontend packages and lockfile; npm audit reports zero known advisories. Removed tracked node_modules. Node 22 builds the frontend/runtime tools.
- Added two foreign-key indexes, optimized ownership policies, and kept job/credential/backup tables inaccessible to browser roles. Database changes remain compatible with the preserved release.

## Validation and limits

Local checks: 230 backend tests, 25 frontend tests, production build and dependency audit. Live database transaction checks verified atomic saving, idempotent retry, conflict preservation and unrelated-account isolation. The expanded browser review checked 54 states at 320, 390, 768 and 1280 pixels with no detected WCAG A/AA violations, horizontal overflow or browser errors. Browser regression scripts cover large transcripts, note versions, slow reads and revoked sessions. Synthetic network timings are not a guarantee for connections from China; origin and database remain in the US.

The recovery workflow restored 238 additional historical frames, with zero note-content changes. Some original sources remain unavailable or require the original local video. Tools & Data reports remaining missing frames instead of silently claiming complete recovery. Private backup restoration was verified by downloading/reconstructing the ZIP and checking every entry. Deployment verifies that the preserved rollback image exists and restores it automatically if release health verification fails.

Job restart reconciliation currently assumes the deployed single application process. Additional replicas require job leases before scaling.
