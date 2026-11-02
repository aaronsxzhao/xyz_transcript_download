# Consistent summary actions and ordered podcast writes

Both episode and video lists expose the same More menu: Delete summary only,
and Delete episode/video. Summary-only deletion retains the list entry, source,
transcript and original media. For videos it removes all generated summary
versions and returns the item to the existing discovered state, ready to process
again. Whole-item deletion retains its existing cancellation and asset cleanup.
Active processing blocks summary-only deletion. Confirmations describe the
scope; cancellation sends no request. Mutation invalidation and revision guards
prevent older episode reads from restoring the deleted summary indicator.

Podcast history writes now compare the existing payload revision inside a
PostgreSQL row lock. Terminal and cancelling states cannot be overwritten by an
incompatible update. Worker writes and terminal recovery carry the queue ID and
worker identity; expired/replaced leases are rejected. Only admission may create
new history, preventing late checkpoints from resurrecting deleted history.
Rejected snapshots reconcile API memory with the winning persisted snapshot.
Embedded API processes refresh durable podcast state as video readers do.

## Release sequence

1. Apply `supabase/migrations/20261102142210_consistent_summary_actions.sql`.
   This adds three SECURITY INVOKER functions, executable only by service_role:
   `save_processing_jobs_ordered`, `delete_user_video_summary`, and
   `delete_user_podcast_summary`. No table changes, historical rewrites, RLS
   changes, or automatic reprocessing. Existing application calls keep working.
2. After all required PR checks pass, use the existing main-branch deployment,
   including worker drain, revision-specific health check and resume.
3. Verify the deployed revision and ordinary health/read paths. Do not delete
   user content as a deployment smoke test.

The production migration attempt was rejected by automatic approval review,
which requires explicit authorization overriding the earlier no-migration audit
boundary. No production migration or application deployment has occurred.

Rollback: revert the application commit using the normal protected workflow and
redeploy. Leave the additive unused functions installed. A rollback does not
restore summaries explicitly deleted by users; the UI confirmation makes that
scope clear. Do not roll back source/transcript data or reprocess user content.

## Validation

- Full backend suite: 1,472 passed; affected suite rerun after final changes.
- Frontend suite: 510 passed. TypeScript/build and existing 197.5 KiB initial
  asset budget pass unchanged; destructive action implementation is loaded on
  demand via the existing taskActions module.
- Real disposable PostgreSQL: concurrent transactions, stale revisions,
  terminal state protection, deleted-job resurrection rejection, worker leases,
  cancellation, ownership, busy deletion, preservation and function permissions.
  `python scripts/check_video_write_order.py` runs this in CI.
- Chromium: 390/1280 px, both list types, classic/editorial themes, cancelled
  confirmation, summary-only deletion, retained source/transcript, reload and
  whole-item deletion. Existing collection/control checks pass at 390/820/1440.
- WebKit requires unavailable local system libraries; required CI runs the same
  new interaction checks in both Chromium and WebKit. Synthetic API fixtures are
  browser verification, not production end-to-end acceptance.
