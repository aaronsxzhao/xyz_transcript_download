# Restore the previous website

## New-content dismissal repair (21 October 2026)

Use `safety/pre-notification-dismiss-20261021`, image
`cfb6fae7b560b6d6fcac41d25690d0ae9c87ed6f`, in **Roll back website**.
This restores the preceding workspace release and is the default fallback for
this notification repair. No database migration is required. Notification
acknowledgements remain saved after rollback; source content is unaffected.

## Workspace and reader iteration (21 October 2026)

Use `safety/pre-workspace-iteration-20261021`, image
`3a2a4fe27aad16d2ff936d787db33042deda5971`, in **Roll back website**.
This restores the release immediately before the workspace/reader changes.
The additive `readable_library` migration only changes a derived view and adds
a count column; it can remain with the previous application. It marks one
empty long-episode summary as needing review instead of advertising it as ready.
No saved summaries, transcripts, media or account settings are deleted.
Browser reading history is optional account-scoped cache and can safely remain.


## Performance backlog checkpoint (21 October 2026)

Use `safety/pre-performance-backlog-20261021`, image
`c5ead130ad344c7b698170e6ce68e6919899b5c3`, in **Roll back website**.
The deployment workflow verifies this image exists before shipping and uses it
as the automatic fallback. This restores the previous visual-language release.

This release adds only a database index and derived private WebP objects.
Original notes, transcripts and images are unchanged. The additive index and
`previews/` objects can safely remain after rollback. The old client rebuilds its
localStorage cache; the new IndexedDB cache is disposable, not a data migration.

## Unified visual language checkpoint (21 October 2026)

Use `safety/pre-visual-language-20261021`, image
`af4de4b581d1bc682877f0cf49c4a68f1625dfc6`, to restore the design before this release.
This is the current automatic health-check fallback. No database migration is
needed, and notes, original media and account settings remain intact. Reading
preferences retain the same keys and work in both versions.

## Pagination and reader checkpoint (21 October 2026)

Use `safety/pre-product-iteration-20261021`, image
`8db4bcd17f03dff9ee0ff40a08389b1636ad0365`, to restore the preceding website.
This was the automatic deployment fallback for that release. The added `library_items`
view and bounded `page_performance` table/function can remain during rollback;
the preceding application does not depend on them. No notes, source images,
transcripts or credentials are modified. Preview files are derived disposable
files in the existing private cache. Do not restore an older database snapshot.


## Workflow reliability checkpoint (20 October 2026)

Use `safety/pre-workflow-review-20261020`, image
`b6dfe4a7345a5b392c0c5f95ca985be2cb10500a`, to undo this workflow review.
This was the automatic deployment fallback for that release. Database records, notes and
media are unchanged; this checkpoint retains the single-column reader.

## Single-column summary checkpoint (20 October 2026)

Use `safety/pre-single-column-summary-20261020`, image
`45b83cd76ee204d2f8cc7462d3a2c095e9a82b03`, to restore the previous two-column
reader. This is the automatic fallback for the single-column release.

## Reader layout checkpoint (20 October 2026)

The version before semantic fallback formatting and bounded screenshot previews
is `safety/pre-reader-layout-20261020`, image
`1275fbc876542df16266ea212084b4db9d8a56f0`. Select that revision in **Roll back
website** to undo the reader changes. It is the automatic health-check fallback
for this release. Notes, original Markdown, screenshots and database schema are
unchanged. This checkpoint retains document-contained startup.

## Document-contained startup checkpoint (20 October 2026)

The preceding release is `safety/pre-document-startup-20261020`, image
`2bee12fc16f122b536fc56adf36c45ee054b3a84`. Use that revision in **Roll back
website**. This is also the automatic health-check fallback for this release.
It restores separate program downloads without changing notes or uploads.
Earlier checkpoints below remain available. Public-shell revalidation supports
both delivery formats and private API/media responses remain network-only.

## Reader/Settings repair checkpoint (20 October 2026)

The version immediately before the reader/Settings loading repair is
`safety/pre-page-repair-20261020`, image
`10ed582f084d2633e7b43e4008f3398c742f33c8`. Use that revision in **Roll back
website**. Deployment health failures restore it automatically.

The public-file worker also revalidates its HTML in the background and prepares
the entry files before offering **Website update ready → Reload**. This handles
the preceding image, which predates the worker. Browser checks exercise an
upgrade followed by a rollback. API responses and private images are never put
in the public-file cache; account data and database schema are unchanged.

The pre-improvement source is retained as the Git tag
`safety/pre-improvements-20261019` (commit `45e995b`). The corresponding live
application image is `440009e42e7574a45fddca717e5451dd98d2cb15`.

In GitHub → Actions → **Roll back website** → **Run workflow**, keep the default
revision to restore that image. The workflow reuses the existing built image,
restarts the website, and verifies its exact revision. No database rows or images
are deleted. Deployment and rollback share a lock to prevent image-tag races.
A failed release health check also restores this preserved image automatically. New deployments must be paused while investigating a rollback.

Application data and generated media are backed up privately before library
recovery. **Private backup and media recovery** verifies a download of every
backup part. Backups are in the private `application-backups` Storage bucket;
they are never uploaded as GitHub artifacts. The manifest lists the parts that
must be concatenated in order to reconstruct the ZIP. Credential values and auth
sessions are excluded; these are application backups, not a full Supabase project
dump. Database schema changes are additive and remain compatible with the old
application. Database rollback scripts accompany any policy changes.

Image recovery only adds missing files. Private recovery journals list the exact
new files and their hashes for targeted reversal if ever needed. Existing notes
and version history are never rewritten during image recovery. Do not restore a
whole historical database snapshot over newer work merely to undo an interface
change.

## Reader and Library repair checkpoint (20 October 2026)

The version immediately before this repair is preserved at
`safety/pre-reader-repair-20261020` (source `14d6561`). To restore that deployed
application, run **Roll back website** with revision
`aca4f9bb29b90cb08b1fef6a97ab4f8efdd3d7e9`. The original October 19 checkpoint
above remains available. This repair changes no saved notes or database schema.

## Startup loading repair checkpoint (20 October 2026)

Before the startup changes, source and image `d3fe060e8e7046a3a359b7f57765f8a38f92a49d`
are preserved at `safety/pre-startup-repair-20261020`. Use that revision in
**Roll back website** to restore the previous reader and Library release.
Earlier checkpoints remain available. These startup changes do not alter notes or schema.
