# Ordered manual note recovery

A manual recovery previously read the task, downloaded a pending copy, then
performed an unconditional final save. A newer generation could commit during
that gap and be replaced by the older copy. A local synthetic reproduction
confirmed the current body changed while the newer historical version remained.

Recovery now uses a dedicated conditional commit. It locks queue admission,
queue records and the task in that order, then checks the observed task revision,
active work, the saved copy's work ID/attempt and its predecessor version IDs.
A mismatch returns a conflict without changing the body or history. A queue
record reclaimed by another worker is fenced by its attempt number as well as ID.
Repeated recovery of the already-current version is a no-op.

New final-save backups capture their predecessor versions and work attempt.
If that metadata read fails, the content is still retained, but marked
unverified. Old backups without generation identity are preserved and refused
for automatic promotion; they are not silently assigned a new generation.
Recovery does not clear the shared pending-copy key, because a concurrent newer
attempt may have replaced it. Normal successful saves retain existing cleanup.
This guarantees recovery cannot override a newer persisted version/attempt; it
does not retroactively reconstruct generation identity for legacy backups.

Install `supabase/migrations/20261103041536_ordered_note_recovery.sql` before
application release. This adds one service-only SECURITY INVOKER function; no
schema restructuring or historical note rewrites. The companion summary-actions
migration is `20261103041517_consistent_summary_actions.sql`.

Validation: SQLite/API tests reproduce completion during backup reads, newer
failed generations, legacy backups, idempotence, newer queued work and reclaimed
attempts. The existing PostgreSQL CI job tests competing connections (new final
save and queue admission versus recovery), history preservation, ownership and
function permissions, using a disposable database. Browser checks cover grouped
multipart navigation and the shared episode/video deletion menu in both engines.

Deploy via the existing main-branch workflow after required CI succeeds, and
verify its exact revision and health. No real user notes are regenerated or
recovered for acceptance. Roll back application through the same workflow and
leave additive functions installed; rollback reintroduces the recovery race,
and must not rewrite or discard notes/version history.
