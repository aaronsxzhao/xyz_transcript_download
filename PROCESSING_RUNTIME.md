# Processing execution and recovery

Supabase deployments enable a private durable queue by default. Set
`PROCESSING_DURABLE_QUEUE=0` to restore the previous scheduler without deleting
notes, transcripts, versions or checkpoints. SQLite development retains the old
scheduler unless explicitly enabled.

At most two tasks run, with at most two independent transcript/summary chunks per
task. Results merge in source order. FFmpeg encoding remains serialized to avoid
saturating the current two CPUs. Successful transcription chunks, model responses,
audits and editorial passes are retained for 30 days. Cache identity includes
source bytes/request, endpoint, model, execution options and actual prompts;
credentials are excluded. Failed/malformed responses are not checkpointed.
Completed transcripts and notes are retained independently of temporary caches.

Workers renew a 90-second lease every three seconds. A killed worker's task is
reclaimed after lease expiry, reusing completed chunks. In-flight requests without
a completed checkpoint can repeat and incur another provider charge. Three
unplanned interruptions require manual Retry; planned pauses do not consume that
budget. Cancel/delete requests are persistent. Final cloud notes and podcast
transcript replacement verify and lock the lease inside the database transaction.

Deployment requests an expiring drain and waits for active tasks to reach saved
boundaries before restart. On initial rollout, untracked legacy work must finish.
After eight minutes without a safe boundary, deployment aborts. Its `always()`
cleanup removes only that release's drain. Old build cancellation also protects
this new release step.

`GET /api/processing/metrics/{podcast|video}/{task_id}` exposes only the signed-in
account's attempt/state, checkpoint hits, active wall time and cumulative stage
request durations. Concurrent durations can exceed wall time.

## Worker roles and current infrastructure

- `PROCESSING_ROLE=embedded` (default): API and dispatcher together.
- `PROCESSING_ROLE=api`: API admission/status only, via `uvicorn api.main:app`.
- `python -m api.worker`: independent durable dispatcher.

Both roles require matching release code, database, encryption key and provider
configuration. API-only processes read cloud progress rather than trusting their
own stale task caches. Never expose service-role credentials to the browser.

Production currently has one 2-OCPU/12-GB container instance and no persistent
media volume. An independent worker entry point is implemented; physical worker
isolation has **not** been rolled out. Instance replacement/resource allocation
and shared persistent media require a separate infrastructure change. Local
uploads not yet transcribed still depend on the container's files; instance
replacement cannot preserve those files. Saved transcripts/chunks are durable.
Remote media may need downloading again even when generated chunks are reused.
Do not deploy the API and worker on separate ephemeral filesystems while accepting
local uploads without first providing shared durable media.

## Model controls

Per-account `llm_reasoning_effort` and `llm_service_tier` apply consistently to
summary generation, audits, editorial/language passes, vision and connection
tests. They do not apply to audio transcription. Blank retains provider defaults.
Known direct-provider models expose documented choices. Custom gateway model IDs
do not prove capability: manual compatible values are marked unverified and must
be tested. Accepted parameters do not prove a gateway actually applied them.
There is no universal fast mode; flex does not universally mean lower latency.
Priority/fast/performance availability and billing depend on the provider.
Rejected options are reported, never silently omitted or rerouted.

## Validation and rollback

All queue/checkpoint/control tables have RLS enabled and browser/public privileges
revoked. RPC smoke tests run in rolled-back transactions; CI prints no source or
credentials. The leased-write source migration is idempotent; production applied
its functions in smaller migrations after the connector timed out on the combined
request. Preserve the preceding main/image before release. The old code can run
with these additive migrations; rollback must not drop queue/checkpoint data.
