# Video task write ordering — 2026-11-02

The reproduced failure was two concurrent writes completing in reverse order:
`cancelled` reached storage first, then an older `summarizing` patch replaced it.
The process cache and persisted task consequently disagreed.

The fix serializes writes per task within a process (including final saves),
while the new service-only `update_video_task_ordered` RPC locks the database row
and rejects older event timestamps. It preserves terminal states unless an
explicit retry writes `pending`. Durable worker writes additionally carry their
queue identity and must hold the current lease; terminal recovery cannot write
for a superseded attempt. Rejected optimistic cache entries are invalidated,
not retried as transport failures. Cancellation responses read back the winning
state when a concurrent final save wins.

No public API shape, saved-note structure, or existing RLS policy changes.
Event order uses the existing UTC `updated_at` convention; worker identity and
terminal-state checks additionally protect cancellation and final saves. This
does not establish a distributed total order for arbitrary metadata edits under
clock skew, nor redesign the podcast task state machine.

## Validation

- Full backend suite: 1,464 passed.
- Isolated PostgreSQL 17: old events, terminal success, explicit retries,
  reclaimed leases, cancellation, superseded terminal recovery, service-only
  function grants, and two concurrent transactions holding the same row lock.
- CI includes the PostgreSQL check as a required input of Test Summary, using
  only synthetic records in `video_order_test` and no production credentials.
- Run locally against an empty disposable PostgreSQL database named
  `video_order_test`: `python scripts/check_video_write_order.py` (normal psql
  environment), or pass `--docker-container` for a local test container.

## Deployment and rollback

Apply `20261102132316_ordered_video_task_writes.sql` before deploying Python.
It adds a function only, rewrites no user records, and leaves old application
versions compatible. Validate function definition/grants after applying it.
Then use the existing PR CI, merge, Oracle deployment, and exact-revision health
checks. Never fall back to an unconditional write if the RPC is missing.

To roll back application behavior, deploy the preceding image `7d71cb3` using
the existing rollback workflow. Leave the additive function installed; removing
it while new workers are running would cause write failures. Rolling back also
restores the former ordering risk. No historical data repair is part of this
release. Local race tests are not evidence that a user's production task was
affected or repaired.
