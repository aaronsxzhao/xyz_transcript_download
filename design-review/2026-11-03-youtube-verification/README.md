# UI review — 2026-11-03

- Baseline: `a011c539797eb402d65e0f319f34c8981a3f238a`; application and focused test commit: `1176c4a8e5033bdee7add5b7272986a07520ebc1`; PR #222.
- Scope: user-authorized YouTube verification and debugging, plus isolated yt-dlp cookie files. Keep existing account tabs, upload methods, themes and navigation.
- Environment: local production builds with synthetic API sessions. No real user cookie, payment, deletion or content reprocessing used in browser tests.
- Coverage: Chromium and WebKit, Classic/Editorial × light/dark × 390/820/1440; persisted-theme reload before opening the lazy verification tool, pending/disabled state, metadata/media success and media failure, request payload and horizontal bounds. Results are in `results.json`.

## Findings

| Surface | Evidence | Impact | Status |
| --- | --- | --- | --- |
| Cookie storage during yt-dlp operations | Shared platform file in previous implementation; overlapping real YoutubeDL contexts tested with synthetic cookies | Concurrent operations can overwrite another account's cookie file | Fixed with independently scoped temporary files |
| YouTube settings | Before screenshot has saved-connection status but no explicit connection/download test | A saved cookie gives no evidence of usable provider access | Authorized verification panel added; saved status is not presented as login proof |

## Verification

- 531 frontend tests and 83 related backend tests passed; 34 diagnostic/log tests rerun after final changes.
- `npm --prefix web run build`: passes TypeScript and unchanged initial-asset budget (197.7 KiB / 197.75 KiB).
- `python scripts/check_youtube_verification_browser.py` and `--webkit`: 24 combinations passed after persisted-theme reload.
- Baseline screenshot comes from a fresh production build of the baseline source, not the checked-in dist snapshot.
- Manually inspected: `before-mobile.png`, `after-mobile.png`, `after-tablet.png`. Other browser states were asserted/captured, not all manually inspected.
- Unit/API tests also cover invalid target URLs, session owner selection, unauthenticated rejection, duplicate-request throttling, session-change reset, request deadline, bounded media reads, HTML-error rejection, process-group termination, cookie cleanup and sanitized diagnostics.
- Local fixtures do not prove that production YouTube currently accepts the saved cookie or server IP. No physical-device acceptance or broad accessibility compliance is claimed.

## Delivery

- PR: https://github.com/aaronsxzhao/xyz_transcript_download/pull/222
- New verification action is explicitly authorized by the user; no user token minting, new admin HTTP endpoint, or production key export is introduced.
- Full CI and deployment verification are recorded in the PR/turn delivery report after these evidence files. A normal signed-in request to the deployed verification endpoint remains necessary for live provider acceptance.
