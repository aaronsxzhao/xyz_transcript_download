# Generation-scoped recovery backups

## Problem and behavior

Before this change, attempts for one task uploaded and deleted the same pending-save object. A delayed old upload could replace a new failed-save backup, and old completion cleanup could remove it.

New writes use `pending-v2/<owner-task-hash>/<payload-hash>.json` in the existing private application-backups bucket and the corresponding local `pending_note_saves/v2` directory. The payload hash includes the version, queue identity, attempt, content and a timestamp captured before storage I/O. Local writes atomically create a unique object with a private temporary file; cloud writes prohibit overwrite. Repeated uploads only count as successful after exact-content verification. Cleanup removes only the exact copy associated with the completed save.

Recovery discovery combines local and paginated cloud copies, retains legacy reads, and prefers the latest durable queue identity and attempt. Upload completion time does not determine the current attempt. Existing transactional recovery checks remain authoritative for activity, version ancestry, task revision and ownership. No schema migration, permission change or automatic content recovery is introduced.

## Release and rollback

Use the existing deployment drain to stop old workers. New and old storage prefixes do not collide; new cleanup never removes shared legacy keys. Do not bulk delete or migrate old backups. This release does not introduce automatic pruning of failed-generation copies.

If reverting the writer, retain the v2 reader in the rollback build so users can still discover new-format backups. A full rollback to an older application preserves the objects but cannot discover v2 backups until the compatible reader is restored. Do not copy v2 objects back onto shared legacy keys. Already committed notes and history remain unchanged.

## Validation

Base main: `c388fda15a18ce3fad6baf4b0cdfed6230be9486`.

- Two independent processes: old retain, new retain, old cleanup leaves new backup intact.
- Delayed cloud upload: the newer attempt wins even when an old attempt uploads last and carries a later timestamp; cloud-only lookup is also checked.
- Same version across different attempts uses distinct keys; repeat upload/cleanup is idempotent.
- More than 100 cloud copies exercise pagination; legacy compatibility and account isolation checked.
- Surviving new backup successfully recovers through the actual SQLite transaction; no old history version is inserted.
- Existing atomic-save and ordered-recovery regressions retained.
- Full backend suite: 1,594 tests passed locally. Cloud storage tests use an in-memory stub; not a real Supabase storage concurrency acceptance test. No production content was reprocessed or recovered.

CI and deployed revision/health are recorded in the PR and release message. No frontend behavior or assets changed.
