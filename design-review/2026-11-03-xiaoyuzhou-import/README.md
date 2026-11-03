# Xiaoyuzhou subscription import — 2026-11-03

- Baseline: main `8ae4fe5e07e0a9eb98f4f67746978f9d368818d3`; isolated `fix/xiaoyuzhou-subscriptions`; no open PRs at start.
- Scope: correct confirmed source parsing, input validation and error feedback. Retain Settings location, layouts, themes and import API field name.

## Findings

1. The form advertised nickname lookup, but the client treated nicknames as user IDs. Accept actual 24-character IDs and official profile share URLs; explain the supported input.
2. A real public profile returned HTTP 200 with subscription counts, owned podcasts and recent plays, but no subscribed podcast list. The old generic podcast/DOM fallback could import unrelated owned shows. Only explicit subscription arrays are accepted now. Missing data raises 422 before any database writes; empty arrays and transport errors remain distinct.
3. Import errors parsed gateway HTML as JSON. Use the shared safe API error parser.

The read-only public-source check used an official podcast page to discover a public podcaster profile. It reported 495 real subscriptions / 492 viewer-visible subscriptions and six owned podcasts, without exposing the subscribed list. The new client rejected this real response with the expected 422. No user body or identifiers are stored in this report.

## Verification

- Full backend: 1,586 passed. Focused source/API regressions: 41 passed.
- Full frontend: 79 files / 534 tests passed.
- Production build passed the unchanged 197.75 KiB compressed budget (197.7 KiB).
- `check_subscription_import.py`: Chromium and WebKit, Classic/Editorial × dark/light × 390/820/1440 px (24 combinations), all passed. Persisted-theme reloads, failure, retry, synthetic success, retained input, safe gateway errors and no horizontal overflow.
- Before screenshot uses the baseline production build and synthetic API failure. After screenshots use the changed production build and synthetic unavailable-source response. Manually inspected `before.png` and `chromium/390-editorial-light-unavailable.png`; remaining screenshots captured with automated assertions.
- Tests use synthetic subscription writes only. The real source check is read-only. No production account subscriptions were imported or changed; no physical-device acceptance claimed.

## Delivery and limitations

This correction does not restore bulk import when the source omits its subscription list. Individual podcast share links remain available through Podcasts → Add Podcast. A dependable bulk source requires a separately designed, user-authorized account integration or export input; this patch does not reuse CLI-global credentials.

PR, CI and production deployment results are recorded in the PR and accompanying delivery message. Authenticated live import UI was not exercised: the diagnostic token deliberately has no subscription-write permission. Local browser fixtures are not production import verification.
