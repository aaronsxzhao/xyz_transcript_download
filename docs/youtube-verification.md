# YouTube verification and debugging

In **Settings → Platform Accounts → YouTube**, save a fresh Netscape cookies.txt file, then select **Verify connection and download**. Optionally enter a particular YouTube video URL. The default is a public test video. Opening Settings does not run a probe automatically.

The authenticated endpoint `POST /api/cookies/youtube/verify` accepts only `{"video_url":"https://www.youtube.com/watch?v=..."}` (or `{}`). It obtains the owner from the normal session, reads only that account's saved YouTube cookie, and runs the same yt-dlp option builder and isolated cookie context used by downloads. It does not accept an account ID or cookie in the request.

The result separates cookie presence, metadata access and a native HTTPS media sample (at most 64 KiB). A successful public-video test does not prove that login-only videos or a full video-processing job will succeed. `no_media` means no direct format was available for the bounded probe; it does not establish that all streaming transports fail. An expired-cookie warning remains a failure even if a public media sample was accessible.

The child process has a 40-second cap and is killed with its process group on timeout; the cookie directory is then removed. The API budgets up to 45 seconds including credential reads. Two probes can run per API process, with a 30-second account cooldown after completion. Cookies use independent 0600 temporary files for each yt-dlp session, including normal downloads and channel extraction.

## Interpreting a report

- `cookie_expired` / `invalid_cookie`: re-export from a logged-in browser and import again.
- `sign_in_or_bot_challenge`: refresh cookies; a persistent result may indicate server-IP restrictions.
- `forbidden` / `rate_limited`: check the stage and try later; compare another permitted video to separate source restrictions from server access.
- `runtime_missing`: check Node/Deno and yt-dlp-ejs in the deployed image.
- `network_error` / `timeout`: check production DNS, TLS and outbound connectivity.
- `no_media` / `invalid_media`: metadata is insufficient to establish downloadable media; inspect the extractor version and provider format changes.
- `storage_unavailable`: account storage failed; do not treat it as missing cookies.

Use **Copy diagnostic report** to share the reference, version, stages and runtime versions. It contains no cookie, account ID, video title, or signed media URL. Existing **Inspect processing runtime** logs expose only the last five whitelisted YouTube diagnostic summaries. Do not export raw runtime logs, which may contain unrelated sensitive data.

Operators with existing authorized access **inside the application runtime** can run:

```sh
python -m scripts.verify_youtube --user-id ACCOUNT_UUID --url https://www.youtube.com/watch?v=VIDEO_ID
```

The account must authorize cookie use. This command uses the runtime's existing cookie manager and returns a sanitized report; it does not fetch production keys, mint user tokens, or create a remote admin endpoint. Do not place production credentials in CI or a local shell to run it. Prefer the signed-in web UI when no authorized runtime shell exists.

Tests use synthetic sessions and controlled media responses. They establish isolation, request boundaries and UI behavior; only a report from the deployed server establishes actual provider access for the tested video.
