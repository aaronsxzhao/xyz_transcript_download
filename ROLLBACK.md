# Restore the previous website

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
