# Scoped platform diagnostics

Platform test tokens are opaque `ptt_` credentials, not Supabase user JWTs. The server
stores only SHA-256 digests. Each token binds exactly one explicitly authorized account,
expires in at most 90 days, and can be revoked immediately. Ordinary user authentication
is unchanged. The registry and quota RPC grant access only to the server's service role.

The exact route-template allowlist in `api/test_access.py` covers podcast episodes,
video/article tasks across platforms, library, collections, summaries, transcripts,
versions, jobs and account status. New routes are denied until reviewed. Cookie values,
auth sessions, exports/backups, administrative endpoints and production mutations are
not granted. Tokens are accepted only in Authorization headers, never query strings.

Scopes:

- `content:read`: up to 120 requests/minute.
- `diagnostics:run`: saved-cookie Bilibili/Douyin checks and YouTube sample download.
- `models:probe`: saved provider model listing and synthetic summary/transcription tests.

Diagnostic and model probes share a six-request/hour budget, atomically enforced across
workers. A request consumes budget before execution, including failed probes. Model
probes cannot override keys, endpoints or models. Content is never auto-reprocessed.
Destructive fixture testing is not enabled: it requires a separately provisioned test
account and reviewed write routes; this credential cannot mutate production content.

## Provision / rotate / revoke

1. Apply the reviewed `scoped_platform_test_tokens` migration.
2. Run `python scripts/create_platform_test_token.py --owner <authorized-account-uuid>
   --output <new-private-file> --days 30`. Output contains only a digest and registry
   metadata. Insert that metadata into `public.platform_test_tokens` through the authorized
   database administration tool. Never insert the plaintext token.
3. Set the repository Actions secret using
   `gh secret set PLATFORM_TEST_TOKEN < <private-file>`; never print the file or put its
   contents in command arguments. Keep it only in an approved secret store.
4. Run `python -m scripts.platform_diagnostics` with the secret bound to
   `PLATFORM_TEST_TOKEN`. Optional explicit `--probe youtube` or `--probe models` performs
   a real deployed probe; normal post-deploy runs only read content/status.
5. Rotate by creating/registering a new token, replacing the Actions secret, verifying
   it, then setting the old row's `revoked_at=now()`. Expired/revoked tokens return 401.
   Registry failures return 503 and never fall back to JWT verification.

Rollback: revert application auth dispatch and diagnostic workflow together; keep the
registry inaccessible to public roles and revoke issued tokens. No content data migration
or history changes are involved.

## Evidence, 2026-11-03

The workspace proxy rejects CONNECT to youtube.com, www.youtube.com, youtu.be,
i.ytimg.com and googlevideo.com with 403 before TLS. Google, GitHub and the production
health endpoint connect successfully through the same proxy. The managed environment
reports unrestricted HTTP networking; it exposes no policy reason for this selective
denial. This is a workspace egress restriction, not proof of a production downloader
failure. Changing the application's cookies cannot repair the workspace CONNECT denial.

Production diagnostic run 41676760818 observed three model-list AuthenticationError
records, zero provider 5xx probe records, and two app `/api/settings/models` 502 access
records. These bounded logs cannot correlate the user's Cloudflare reference to an exact
request. The application previously mapped every provider exception to 502. Provider
credential/configuration rejections now return 422, rate limiting 429; actual upstream
5xx remain 502. Error messages remain redacted and never log keys/provider bodies.
